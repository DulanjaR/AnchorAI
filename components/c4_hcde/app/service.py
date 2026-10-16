"""HCDE service: the full loop on top of the database.

recommend -> respond (user may override the tier) -> outcome -> (probe -> grade) -> profile updates.

Capability Ledger: help is recorded as BORROWED capability (weight grows with the tier); an
unaided success adds BUILT capability; a passed PROBE REPAYS borrowed help on that skill.
Memory (RAG): the user's own past interactions are retrieved by similarity and summarised into the
explanation ("you solved 2 similar tasks unaided"). Memory informs the explanation and the student;
the tier itself is always decided by the interpretable layer.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..decision import bkt
from ..decision.engine import SkillState, recommend
from ..decision.task_analyzer import analyze, for_matching
from ..decision.text_index import HybridIndex
from ..generation.base import generate, grade_probe
from ..training.compliance import split_probe
from .db.models import Interaction, LedgerEntry, Probe, SkillStateRow

BORROW = {"HUMAN_FIRST": 0.0, "HINT": 0.25, "GUIDED": 0.5, "SHARED": 0.75, "EMERGENCY": 1.0}
TIERS = list(BORROW)


class NotFound(Exception):
    pass


def _state_row(db: Session, user_id: str, skill: str) -> SkillStateRow:
    row = db.get(SkillStateRow, (user_id, skill))
    if row is None:
        row = SkillStateRow(user_id=user_id, skill=skill, mastery=bkt.P_INIT, observations=0, success_streak=0,
                            fail_streak=0, borrowed=0.0, built=0.0, repaid=0.0)
        db.add(row)
    return row


def _as_state(row: SkillStateRow) -> SkillState:
    return SkillState(mastery=row.mastery, observations=row.observations, success_streak=row.success_streak,
                      fail_streak=row.fail_streak, last_tier=row.last_tier,
                      borrowed=row.borrowed, built=row.repaid)  # engine compares help borrowed vs repaid


def memory(db: Session, user_id: str, task: str, k: int = 3, min_sim: float = 0.1) -> dict:
    """Retrieve the user's most similar past interactions (with known outcomes)."""
    past = db.scalars(select(Interaction).where(Interaction.user_id == user_id, Interaction.outcome.is_not(None))
                      .order_by(Interaction.id.desc()).limit(200)).all()
    if not past:
        return {"similar": [], "note": None}
    index = HybridIndex([for_matching(p.task) for p in past])
    floor = 0.6 if index.mode == "embedding" else min_sim
    hits = [(past[i], s) for i, s in index.search(for_matching(task), k) if s >= floor]
    similar = [{"interaction_id": p.id, "task": p.task[:120], "skill": p.skill, "tier": p.chosen_tier,
                "outcome": p.outcome, "similarity": round(s, 3)} for p, s in hits]
    solved = [x for x in similar if x["outcome"] == "solved"]
    unaided = [x for x in solved if x["tier"] in ("HUMAN_FIRST", "HINT")]
    note = None
    if unaided:
        note = f"you solved {len(unaided)} similar task{'s' if len(unaided) > 1 else ''} before with little or no help"
    elif solved:
        note = f"you solved {len(solved)} similar task{'s' if len(solved) > 1 else ''} before with support"
    return {"similar": similar, "note": note, "mode": index.mode}


def recommend_for(db: Session, user_id: str, task: str, minutes_left: float | None = None,
                  difficulty_hint: int | None = None) -> Interaction:
    profile = analyze(task, minutes_left, difficulty_hint)
    row = _state_row(db, user_id, profile.skill)
    mem = memory(db, user_id, task)
    decision = recommend(profile, _as_state(row), mem["note"])
    d = decision.to_dict()
    d["memory"] = mem
    d["skill_state"] = {"mastery": round(row.mastery, 3), "observations": row.observations,
                        "borrowed": round(row.borrowed, 2), "repaid": round(row.repaid, 2), "built": round(row.built, 2)}
    it = Interaction(user_id=user_id, task=task, skill=profile.skill, module=profile.module,
                     difficulty=profile.difficulty, urgency=profile.urgency, profile=profile.to_dict(),
                     decision=d, recommended_tier=decision.tier)
    db.add(it)
    db.commit()
    return it


def respond(db: Session, interaction_id: int, tier: str | None = None, student_attempt: str | None = None,
            call=None) -> Interaction:
    it = db.get(Interaction, interaction_id)
    if it is None:
        raise NotFound(interaction_id)
    chosen = tier or it.recommended_tier
    if chosen not in TIERS:
        raise ValueError(f"unknown tier {chosen}")
    gen = generate(it.task, chosen, student_attempt, call=call)
    it.chosen_tier, it.overridden, it.reply, it.generation = chosen, chosen != it.recommended_tier, gen.text, gen.to_dict()
    row = _state_row(db, it.user_id, it.skill)
    if BORROW[chosen] > 0:
        row.borrowed += BORROW[chosen]
        db.add(LedgerEntry(user_id=it.user_id, skill=it.skill, kind="borrowed", amount=BORROW[chosen],
                           interaction_id=it.id, note=f"{chosen} help"))
    db.commit()
    return it


def record_outcome(db: Session, interaction_id: int, solved: bool) -> dict:
    it = db.get(Interaction, interaction_id)
    if it is None:
        raise NotFound(interaction_id)
    tier = it.chosen_tier or it.recommended_tier
    row = _state_row(db, it.user_id, it.skill)
    u = bkt.update(row.mastery, tier, solved)
    row.mastery, row.observations, row.last_tier = u.after, row.observations + 1, tier
    row.success_streak, row.fail_streak = (row.success_streak + 1, 0) if solved else (0, row.fail_streak + 1)
    it.outcome = "solved" if solved else "not_solved"
    if solved and tier == "HUMAN_FIRST":
        row.built += 1.0
        db.add(LedgerEntry(user_id=it.user_id, skill=it.skill, kind="built", amount=1.0, interaction_id=it.id,
                           note="solved without AI help"))
    db.commit()
    return {"interaction_id": it.id, "skill": it.skill, "bkt": vars(u), "ledger": ledger_for(db, it.user_id, it.skill)}


def create_probe(db: Session, user_id: str, skill: str | None = None, interaction_id: int | None = None,
                 call=None) -> Probe:
    """A short unaided check on the same skill as a past task (default: the skill with most unrepaid help)."""
    if interaction_id:
        src = db.get(Interaction, interaction_id)
    else:
        if skill is None:
            rows = db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == user_id)).all()
            if not rows:
                raise NotFound("no skills yet")
            skill = max(rows, key=lambda r: r.borrowed - r.repaid).skill
        src = db.scalars(select(Interaction).where(Interaction.user_id == user_id, Interaction.skill == skill)
                         .order_by(Interaction.id.desc())).first()
    if src is None:
        raise NotFound("no task to build a probe from")
    gen = generate(src.task, "PROBE", call=call)
    parts = split_probe(gen.text) or (gen.text, "")
    p = Probe(user_id=user_id, skill=src.skill, source_task=src.task, problem=parts[0].strip(),
              answer_key=parts[1].strip())
    db.add(p)
    db.commit()
    return p


def answer_probe(db: Session, probe_id: int, answer: str, call=None) -> dict:
    p = db.get(Probe, probe_id)
    if p is None:
        raise NotFound(probe_id)
    g = grade_probe(p.problem, p.answer_key, answer, call=call)
    p.answer, p.feedback, p.status = answer, g["feedback"], "passed" if g["pass"] else "failed"
    row = _state_row(db, p.user_id, p.skill)
    u = bkt.update(row.mastery, "PROBE", g["pass"])
    row.mastery, row.observations = u.after, row.observations + 1
    row.success_streak, row.fail_streak = (row.success_streak + 1, 0) if g["pass"] else (0, row.fail_streak + 1)
    if g["pass"]:
        repay = round(min(1.0, max(0.0, row.borrowed - row.repaid)), 2)
        row.repaid += repay
        row.built += 1.0
        db.add(LedgerEntry(user_id=p.user_id, skill=p.skill, kind="repaid", amount=repay, probe_id=p.id,
                           note="passed an unaided check"))
        db.add(LedgerEntry(user_id=p.user_id, skill=p.skill, kind="built", amount=1.0, probe_id=p.id,
                           note="passed an unaided check"))
    db.commit()
    return {"probe_id": p.id, "passed": g["pass"], "feedback": g["feedback"], "bkt": vars(u),
            "ledger": ledger_for(db, p.user_id, p.skill)}


def ledger_for(db: Session, user_id: str, skill: str | None = None) -> dict | list[dict]:
    q = select(SkillStateRow).where(SkillStateRow.user_id == user_id)
    if skill:
        q = q.where(SkillStateRow.skill == skill)
    rows = db.scalars(q).all()
    out = [{"skill": r.skill, "mastery": round(r.mastery, 3), "observations": r.observations,
            "borrowed": round(r.borrowed, 2), "repaid": round(r.repaid, 2), "built": round(r.built, 2),
            "outstanding": round(r.borrowed - r.repaid, 2), "last_tier": r.last_tier} for r in rows]
    if skill:
        return out[0] if out else {}
    return sorted(out, key=lambda x: -x["outstanding"])
