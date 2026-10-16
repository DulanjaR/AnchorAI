"""Decision engine: combines task profile, skill state, scoring, fading and explanation.

Pure function over plain data, so it is easy to test and to explain. The API layer loads the
user's skill state from the database, calls recommend(), and stores the result.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from . import explain as ex
from .fading import adjust
from .scoring import score
from .task_analyzer import TaskProfile

TIERS = ["HUMAN_FIRST", "HINT", "GUIDED", "SHARED", "EMERGENCY"]


@dataclass
class SkillState:
    mastery: float = 0.3
    observations: int = 0
    success_streak: int = 0
    fail_streak: int = 0
    last_tier: str | None = None
    borrowed: float = 0.0     # Capability Ledger: help received and not yet repaid by an unaided check
    built: float = 0.0
    prior_note: str | None = None  # why the starting estimate is what it is (transfer from related skills)
    novelty: float = 0.0           # 1 first task in this language/tool, 0.5 new skill in a known one, else 0


@dataclass
class Decision:
    tier: str
    base_tier: str
    need: float
    factors: dict
    contributions: dict
    emergency_rule: bool
    fading_reason: str | None
    suggest_probe: bool
    explanation: str
    alternatives: list[str]

    def to_dict(self) -> dict:
        return asdict(self)


PROBE_DEBT = 1.5  # suggest an unaided check when this much help on a skill is still unrepaid


def recommend(profile: TaskProfile, state: SkillState, memory_note: str | None = None) -> Decision:
    s = score(state.mastery, profile.difficulty, profile.urgency, state.fail_streak,
              unknown_skill=profile.skill == "general", novelty=state.novelty)
    tier, reason = (s.tier, None) if s.emergency_rule else adjust(
        s.tier, state.last_tier, state.success_streak, state.fail_streak)
    debt = round(state.borrowed - state.built, 2)
    suggest_probe = debt >= PROBE_DEBT and not s.emergency_rule
    text = ex.explain(tier, profile.skill, state.mastery, state.observations, profile.difficulty, profile.urgency,
                      profile.minutes_left, s.contributions, s.emergency_rule, reason, memory_note,
                      context=profile.context, prior_note=state.prior_note)
    if suggest_probe:
        text += (f" You have relied on help for {profile.skill.replace('-', ' ')} a few times; "
                 f"a quick 5-minute check would turn that into skill you have shown yourself.")
    return Decision(tier=tier, base_tier=s.tier, need=s.need, factors=s.factors, contributions=s.contributions,
                    emergency_rule=s.emergency_rule, fading_reason=reason, suggest_probe=suggest_probe,
                    explanation=text, alternatives=[t for t in TIERS if t != tier])
