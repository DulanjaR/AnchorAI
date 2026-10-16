"""Transparent rules: need score -> assistance tier.

need = weighted sum of interpretable factors (each 0..1). The weights and thresholds are fixed and
documented here, so every decision can be explained factor by factor. EMERGENCY is not reached by
the score; it needs real time pressure (rule below), so the system never hands out full solutions
just because a task is hard.
"""
from __future__ import annotations

from dataclasses import dataclass

WEIGHTS = {"gap": 0.45, "difficulty": 0.25, "urgency": 0.20, "recent_struggle": 0.10}
THRESHOLDS = [(0.30, "HUMAN_FIRST"), (0.45, "HINT"), (0.62, "GUIDED"), (1.01, "SHARED")]
EMERGENCY_URGENCY, EMERGENCY_MAX_MASTERY = 0.8, 0.6


@dataclass
class Score:
    need: float
    tier: str
    factors: dict[str, float]        # factor -> its value (0..1)
    contributions: dict[str, float]  # factor -> weight * value
    emergency_rule: bool


def score(mastery: float, difficulty: int, urgency: float, fail_streak: int, unknown_skill: bool = False) -> Score:
    factors = {
        "gap": 1 - mastery,
        "difficulty": (difficulty - 1) / 4,
        "urgency": urgency,
        "recent_struggle": min(1.0, fail_streak / 2),
    }
    contributions = {k: round(WEIGHTS[k] * v, 3) for k, v in factors.items()}
    need = round(sum(contributions.values()), 3)
    tier = next(t for limit, t in THRESHOLDS if need < limit)
    emergency = urgency >= EMERGENCY_URGENCY and mastery < EMERGENCY_MAX_MASTERY and not unknown_skill
    if emergency:
        tier = "EMERGENCY"
    return Score(need, tier, {k: round(v, 3) for k, v in factors.items()}, contributions, emergency)
