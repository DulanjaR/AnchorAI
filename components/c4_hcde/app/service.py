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
from ..decision.context import label as ctx_label
from ..decision.task_analyzer import analyze, for_matching
from ..decision.text_index import HybridIndex
from ..generation.base import generate, grade_probe
from ..training.compliance import split_probe
from ..generation.check import check as check_answer_text
from .db.models import Calibration, Check, Interaction, LedgerEntry, Probe, SkillStateRow

BORROW = {"HUMAN_FIRST": 0.0, "HINT": 0.25, "GUIDED": 0.5, "SHARED": 0.75, "EMERGENCY": 1.0}
TIERS = list(BORROW)


class NotFound(Exception):
    pass


# Transfer prior: how much a new (skill, context) starts from what the student already showed elsewhere.
# The same concept in a related context transfers in proportion to how similar the contexts are
# (decision/context.py: Python->Java 0.65, report->essay 0.6, SQL->essay 0.2); the subject transfers a little.
MAX_SAME_SKILL, W_MODULE, PRIOR_CAP = 0.6, 0.25, 0.75


# ---------------------------------------------------------------- first-task calibration
CONFIDENCE_PRIOR = {1: 0.10, 2: 0.25, 3: 0.40, 4: 0.55, 5: 0.70}
EXPERIENCE_SHIFT = {"never": -0.08, "a_few": 0.0, "often": 0.08}
EXPERIENCE_TEXT = {"never": "never done tasks like this", "a_few": "done tasks like this a few times",
                   "often": "often done tasks like this"}
SELF_REPORT_WEIGHT = 0.5  # the rest is the fitted population prior; evidence takes over after that


def calibration_questions(module: str) -> list[dict]:
    subject = module if module and module != "General" else "this subject"
    return [
        {"id": "confidence", "text": f"How confident do you feel with {subject} tasks like this one?",
         "type": "scale", "min": 1, "max": 5, "labels": {"1": "not at all", "3": "somewhat", "5": "very"}},
        {"id": "experience", "text": "How often have you done tasks like this before?", "type": "choice",
         "options": [{"value": "never", "label": "Never"}, {"value": "a_few", "label": "A few times"},
                     {"value": "often", "label": "Often"}]},
        {"id": "preference", "text": "When you start a task, what do you usually prefer?", "type": "choice", "optional": True,
         "note": "Saved for your profile; it does not change the recommendation, and you can always pick another level.",
         "options": [{"value": "try_first", "label": "Try it myself first"},
                     {"value": "guidance_early", "label": "Some guidance early on"}]},
    ]


def needs_calibration(db: Session, user_id: str, module: str) -> bool:
    """Only before the first task in a subject: no calibration yet and no observed history there."""
    if db.get(Calibration, (user_id, module)) is not None:
        return False
    seen = db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == user_id, SkillStateRow.module == module,
                                                  SkillStateRow.observations > 0)).first()
    return seen is None


def _self_report(db: Session, user_id: str, module: str) -> tuple[float, str] | None:
    c = db.get(Calibration, (user_id, module))
    if c is None:
        return None
    est = CONFIDENCE_PRIOR.get(c.confidence, 0.4) + EXPERIENCE_SHIFT.get(c.experience, 0.0)
    note = (f"from your answers: confidence {c.confidence}/5 and you have {EXPERIENCE_TEXT.get(c.experience, c.experience)}; "
            "this is only a starting point until you complete tasks")
    return min(0.8, max(0.05, est)), note


def calibrate(db: Session, user_id: str, module: str, confidence: int, experience: str,
              preference: str | None = None) -> dict:
    """Store the answers and re-seed any skill in this subject that has no observations yet."""
    if confidence not in CONFIDENCE_PRIOR or experience not in EXPERIENCE_SHIFT:
        raise ValueError("confidence must be 1-5 and experience one of never / a_few / often")
    c = db.get(Calibration, (user_id, module))
    if c is None:
        c = Calibration(user_id=user_id, module=module, confidence=confidence, experience=experience, preference=preference)
        db.add(c)
    else:
        c.confidence, c.experience, c.preference = confidence, experience, preference
    db.flush()
    reseeded = []
    for row in db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == user_id, SkillStateRow.module == module,
                                                      SkillStateRow.observations == 0)).all():
        p, note = _prior(db, user_id, row.skill, row.context, module)
        row.prior = row.mastery = p
        row.prior_note = note
        reseeded.append({"skill": row.skill, "context": row.context, "prior": round(p, 3)})
    db.commit()
    return {"user_id": user_id, "module": module, "confidence": confidence, "experience": experience,
            "preference": preference, "reseeded": reseeded}


def _prior(db: Session, user_id: str, skill: str, context: str, module: str,
           difficulty: int | None = None) -> tuple[float, str | None]:
    """Starting mastery for a skill-context the student has never done (near vs far transfer). With no
    related history it is the fitted population prior for the task's difficulty (decision/bkt_fit.py)."""
    base = bkt.prior_for(difficulty)
    from ..decision.context import similarity as ctx_sim
    rows = db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == user_id,
                                                  SkillStateRow.observations > 0)).all()
    same = [r for r in rows if r.skill == skill and r.context != context]
    mod = [r for r in rows if r.module == module and r.skill != skill]
    if not same and not mod:
        sr = _self_report(db, user_id, module)
        if sr:  # first task in this subject: blend the population prior with what the student told us
            return round(min(PRIOR_CAP, SELF_REPORT_WEIGHT * sr[0] + (1 - SELF_REPORT_WEIGHT) * base), 3), sr[1]
        return base, None
    best = max(same, key=lambda r: ctx_sim(r.context, context) * r.mastery) if same else None
    w_same = min(MAX_SAME_SKILL, ctx_sim(best.context, context)) if best else 0.0
    mod_m = sum(r.mastery for r in mod) / len(mod) if mod else 0.0
    w_mod = min(W_MODULE, 1 - w_same) if mod else 0.0
    p = w_same * (best.mastery if best else 0) + w_mod * mod_m + (1 - w_same - w_mod) * base
    p = round(min(PRIOR_CAP, max(0.05, p)), 3)
    if best:
        verb = "strong at" if best.mastery >= 0.7 else "working on"
        near = "a closely related" if ctx_sim(best.context, context) >= 0.6 else "a different"
        note = (f"you are {verb} {skill.replace('-', ' ')} in {ctx_label(best.context)} ({near} context), "
                f"and this is your first time in {ctx_label(context)}")
    else:
        note = f"this is a new skill for you, but you have practised other {module} skills"
    return p, note


def _state_row(db: Session, user_id: str, skill: str, context: str = "general", module: str = "General",
               difficulty: int | None = None) -> SkillStateRow:
    row = db.get(SkillStateRow, (user_id, skill, context))
    if row is None:
        p, note = _prior(db, user_id, skill, context, module, difficulty)
        row = SkillStateRow(user_id=user_id, skill=skill, context=context, module=module, mastery=p, prior=p,
                            prior_note=note, observations=0, success_streak=0, fail_streak=0,
                            borrowed=0.0, built=0.0, repaid=0.0)
        db.add(row)
        db.flush()
    return row


def _novelty(db: Session, row: SkillStateRow) -> float:
    """Unfamiliar language/tool relative to the student's own track record. A brand-new student gets 0:
    with no history, the skill gap already expresses the uncertainty."""
    if row.observations > 0 or row.context == "general":
        return 0.0
    any_history = db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == row.user_id,
                                                         SkillStateRow.observations > 0)).first()
    if not any_history:
        return 0.0
    known = db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == row.user_id,
                                                   SkillStateRow.context == row.context,
                                                   SkillStateRow.observations > 0)).first()
    return 0.5 if known else 1.0


def _as_state(row: SkillStateRow, novelty: float = 0.0) -> SkillState:
    return SkillState(novelty=novelty, mastery=row.mastery, observations=row.observations, success_streak=row.success_streak,
                      fail_streak=row.fail_streak, last_tier=row.last_tier,
                      borrowed=row.borrowed, built=row.repaid,  # engine compares help borrowed vs repaid
                      prior_note=row.prior_note)


def memory(db: Session, user_id: str, task: str, k: int = 3, min_sim: float = 0.1) -> dict:
    """Retrieve the user's most similar past interactions (with known outcomes)."""
    past = db.scalars(select(Interaction).where(Interaction.user_id == user_id, Interaction.outcome.is_not(None))
                      .order_by(Interaction.id.desc()).limit(200)).all()
    if not past:
        return {"similar": [], "note": None}
    index = HybridIndex([for_matching(p.task) for p in past])
    results = index.search(for_matching(task), k)
    floor = 0.6 if index.last_mode == "embedding" else min_sim
    hits = [(past[i], s) for i, s in results if s >= floor]
    similar = [{"interaction_id": p.id, "task": p.task[:120], "skill": p.skill, "tier": p.chosen_tier,
                "outcome": p.outcome, "similarity": round(s, 3)} for p, s in hits]
    solved = [x for x in similar if x["outcome"] == "solved"]
    unaided = [x for x in solved if x["tier"] in ("HUMAN_FIRST", "HINT")]
    note = None
    if unaided:
        note = f"you solved {len(unaided)} similar task{'s' if len(unaided) > 1 else ''} before with little or no help"
    elif solved:
        note = f"you solved {len(solved)} similar task{'s' if len(solved) > 1 else ''} before with support"
    return {"similar": similar, "note": note, "mode": index.last_mode}


def calibration_for_task(db: Session, user_id: str, task: str) -> dict:
    """Whether to ask the calibration questions before recommending for this task."""
    module = analyze(task).module
    need = needs_calibration(db, user_id, module)
    return {"module": module, "needs_calibration": need, "questions": calibration_questions(module) if need else []}


def recommend_for(db: Session, user_id: str, task: str, minutes_left: float | None = None,
                  difficulty_hint: int | None = None, calibration: dict | None = None) -> Interaction:
    profile = analyze(task, minutes_left, difficulty_hint)
    if calibration:
        calibrate(db, user_id, profile.module, int(calibration["confidence"]), calibration["experience"],
                  calibration.get("preference"))
    row = _state_row(db, user_id, profile.skill, profile.context, profile.module, profile.difficulty)
    mem = memory(db, user_id, task)
    decision = recommend(profile, _as_state(row, _novelty(db, row)), mem["note"])
    d = decision.to_dict()
    d["memory"] = mem
    d["skill_state"] = {"context": row.context, "prior": round(row.prior, 3), "prior_note": row.prior_note,
                        "mastery": round(row.mastery, 3), "observations": row.observations,
                        "borrowed": round(row.borrowed, 2), "repaid": round(row.repaid, 2), "built": round(row.built, 2)}
    it = Interaction(user_id=user_id, task=task, skill=profile.skill, context=profile.context, module=profile.module,
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
    row = _state_row(db, it.user_id, it.skill, it.context, it.module)
    if BORROW[chosen] > 0:
        row.borrowed += BORROW[chosen]
        db.add(LedgerEntry(user_id=it.user_id, skill=it.skill, context=it.context, kind="borrowed", amount=BORROW[chosen],
                           interaction_id=it.id, note=f"{chosen} help"))
    db.commit()
    return it


FEEDBACK_BORROW = 0.1  # each checked-and-corrected attempt is a little help received


def check_answer(db: Session, interaction_id: int, answer: str, call=None) -> dict:
    """Grade the student's own answer; feedback respects the tier they chose. A pass is recorded as a
    VERIFIED solved outcome (stronger evidence than self-report). Corrective feedback counts as a little
    borrowed help, and a pass after several attempts counts as solved-with-help."""
    it = db.get(Interaction, interaction_id)
    if it is None:
        raise NotFound(interaction_id)
    tier = it.chosen_tier or it.recommended_tier
    if not it.reference:
        it.reference = generate(it.task, "EMERGENCY", call=call).text
    res, schema = check_answer_text(it.task, tier, it.context, it.reference, answer, call=call,
                                    sql_schema=it.test_data)
    if schema and not it.test_data:
        it.test_data = schema
    it.checks = (it.checks or 0) + 1
    db.add(Check(interaction_id=it.id, attempt=it.checks, answer=answer, result=res.result, feedback=res.feedback,
                 details=res.to_dict()))
    out = {"interaction_id": it.id, "attempt": it.checks, "tier": tier, **res.to_dict()}
    row = _state_row(db, it.user_id, it.skill, it.context, it.module)
    if res.result != "pass":
        row.borrowed += FEEDBACK_BORROW
        db.add(LedgerEntry(user_id=it.user_id, skill=it.skill, context=it.context, kind="borrowed",
                           amount=FEEDBACK_BORROW, interaction_id=it.id, note="corrective feedback on an answer"))
        db.commit()
        return out
    db.commit()
    if it.outcome is None:
        # solved after corrections = solved with at least hint-level help
        effective = tier if it.checks == 1 else max(tier, "HINT", key=lambda t: TIERS.index(t))
        out["outcome"] = record_outcome(db, it.id, True, verified=True, effective_tier=effective)
    return out


def record_outcome(db: Session, interaction_id: int, solved: bool, verified: bool = False,
                   effective_tier: str | None = None) -> dict:
    it = db.get(Interaction, interaction_id)
    if it is None:
        raise NotFound(interaction_id)
    tier = effective_tier or it.chosen_tier or it.recommended_tier
    row = _state_row(db, it.user_id, it.skill, it.context, it.module)
    u = bkt.update(row.mastery, tier, solved)
    it.verified = verified
    row.mastery, row.observations, row.last_tier = u.after, row.observations + 1, tier
    row.success_streak, row.fail_streak = (row.success_streak + 1, 0) if solved else (0, row.fail_streak + 1)
    it.outcome = "solved" if solved else "not_solved"
    if solved and tier == "HUMAN_FIRST":
        row.built += 1.0
        db.add(LedgerEntry(user_id=it.user_id, skill=it.skill, context=it.context, kind="built", amount=1.0, interaction_id=it.id,
                           note="solved without AI help"))
    db.commit()
    return {"interaction_id": it.id, "skill": it.skill, "context": it.context, "verified": verified,
            "evidence_tier": tier, "bkt": vars(u),
            "ledger": ledger_for(db, it.user_id, it.skill, it.context)}


def create_probe(db: Session, user_id: str, skill: str | None = None, interaction_id: int | None = None,
                 call=None, context: str | None = None) -> Probe:
    """A short unaided check on the same skill as a past task (default: the skill with most unrepaid help)."""
    if interaction_id:
        src = db.get(Interaction, interaction_id)
    else:
        if skill is None:
            rows = db.scalars(select(SkillStateRow).where(SkillStateRow.user_id == user_id)).all()
            if not rows:
                raise NotFound("no skills yet")
            top = max(rows, key=lambda r: r.borrowed - r.repaid)
            skill, context = top.skill, top.context
        q = select(Interaction).where(Interaction.user_id == user_id, Interaction.skill == skill)
        if context:
            q = q.where(Interaction.context == context)
        src = db.scalars(q.order_by(Interaction.id.desc())).first()
    if src is None:
        raise NotFound("no task to build a probe from")
    recent = [i.task for i in db.scalars(select(Interaction).where(Interaction.user_id == user_id,
                                                               Interaction.skill == src.skill,
                                                               Interaction.context == src.context)
                                         .order_by(Interaction.id.desc()).limit(10)).all()]
    gen = generate(src.task, "PROBE", call=call, avoid=recent)
    if not gen.passed:
        # still too close to what the student has seen: build it from a curated reference task of the same skill
        ref = _reference_task(src.skill, exclude=recent)
        if ref:
            alt = generate(ref, "PROBE", call=call, avoid=recent)
            if alt.passed or len(alt.reasons) < len(gen.reasons):
                gen = alt
    parts = split_probe(gen.text) or (gen.text, "")
    p = Probe(user_id=user_id, skill=src.skill, context=src.context, source_task=src.task, problem=parts[0].strip(),
              answer_key=parts[1].strip())
    db.add(p)
    db.commit()
    return p


def _reference_task(skill: str, exclude: list[str]) -> str | None:
    from ..decision.task_analyzer import _reference
    from ..training.compliance import similarity
    tasks, _ = _reference()
    for t in tasks:
        if t["skill"] == skill and all(similarity(t["task"], e) <= 0.4 for e in exclude):
            return t["task"]
    return None


def answer_probe(db: Session, probe_id: int, answer: str, call=None) -> dict:
    p = db.get(Probe, probe_id)
    if p is None:
        raise NotFound(probe_id)
    g = grade_probe(p.problem, p.answer_key, answer, call=call)
    p.answer, p.feedback = answer, g["feedback"]
    p.status = {"pass": "passed", "partial": "partial", "fail": "failed"}[g["result"]]
    row = _state_row(db, p.user_id, p.skill, p.context)
    if g["result"] == "partial":
        # right idea, incomplete: feedback only, no strong evidence either way
        u = bkt.BKTUpdate(round(row.mastery, 4), round(row.mastery, 4), "partial: right idea, incomplete answer")
        row.observations += 1
    else:
        u = bkt.update(row.mastery, "PROBE", g["pass"])
        row.mastery, row.observations = u.after, row.observations + 1
        row.success_streak, row.fail_streak = (row.success_streak + 1, 0) if g["pass"] else (0, row.fail_streak + 1)
        row.last_tier = "PROBE_FAILED" if not g["pass"] else row.last_tier
    if g["pass"]:
        repay = round(min(1.0, max(0.0, row.borrowed - row.repaid)), 2)
        row.repaid += repay
        row.built += 1.0
        db.add(LedgerEntry(user_id=p.user_id, skill=p.skill, context=p.context, kind="repaid", amount=repay, probe_id=p.id,
                           note="passed an unaided check"))
        db.add(LedgerEntry(user_id=p.user_id, skill=p.skill, context=p.context, kind="built", amount=1.0, probe_id=p.id,
                           note="passed an unaided check"))
    db.commit()
    return {"probe_id": p.id, "result": g["result"], "passed": g["pass"], "feedback": g["feedback"], "bkt": vars(u),
            "ledger": ledger_for(db, p.user_id, p.skill, p.context)}


def ledger_for(db: Session, user_id: str, skill: str | None = None, context: str | None = None):
    q = select(SkillStateRow).where(SkillStateRow.user_id == user_id)
    if skill:
        q = q.where(SkillStateRow.skill == skill)
    if context:
        q = q.where(SkillStateRow.context == context)
    rows = db.scalars(q).all()
    out = [{"skill": r.skill, "context": r.context, "module": r.module, "mastery": round(r.mastery, 3),
            "prior": round(r.prior, 3), "prior_note": r.prior_note, "observations": r.observations,
            "borrowed": round(r.borrowed, 2), "repaid": round(r.repaid, 2), "built": round(r.built, 2),
            "outstanding": round(r.borrowed - r.repaid, 2), "last_tier": r.last_tier} for r in rows]
    if skill:
        return out[0] if out else {}
    return sorted(out, key=lambda x: (x["module"], x["skill"], x["context"]))
