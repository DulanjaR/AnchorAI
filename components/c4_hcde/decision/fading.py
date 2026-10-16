"""Progressive fading: step help down after sustained success, back up after failure.

Works on top of the score-based tier. Per (user, skill) we keep a success streak and a failure
streak of the student's recent outcomes. Two successes in a row at a tier -> the next recommendation
is capped one tier lower; a failure -> allowed one tier higher than the score alone suggests.
"""
from __future__ import annotations

TIER_ORDER = ["HUMAN_FIRST", "HINT", "GUIDED", "SHARED", "EMERGENCY"]
STEP_DOWN_AFTER = 2


def adjust(base_tier: str, last_tier: str | None, success_streak: int, fail_streak: int) -> tuple[str, str | None]:
    """Returns (tier, reason or None)."""
    i = TIER_ORDER.index(base_tier)
    if last_tier == "PROBE_FAILED":
        return base_tier, "your last quick check on this skill was not passed yet"
    if last_tier is None or last_tier not in TIER_ORDER:
        return base_tier, None
    j = TIER_ORDER.index(last_tier)
    if success_streak >= STEP_DOWN_AFTER and i >= j and j > 0:
        return TIER_ORDER[j - 1], f"you succeeded {success_streak} times in a row at {last_tier.replace('_', ' ').title()}, so support is reduced one step"
    if fail_streak >= 1 and i <= j and j < len(TIER_ORDER) - 2:  # never auto-escalate into EMERGENCY
        return TIER_ORDER[j + 1], "the last attempt did not succeed, so support is increased one step"
    return base_tier, None
