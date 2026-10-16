"""Bayesian Knowledge Tracing per (user, skill, context), with assistance-dependent guess and slip.

Standard BKT updates P(mastered) from each observed outcome. The HCDE twist: a success only counts
as evidence of the student's OWN capability in proportion to how little help they had. A success
under EMERGENCY (the AI wrote the answer) says nothing about mastery, so it never moves the estimate.
A success with no help (HUMAN_FIRST, or a passed PROBE) is strong evidence. Failures always count.
This is what stops borrowed capability from inflating the profile.

Parameters: guess, slip and learning rate per assistance tier and the starting prior per difficulty
level are fitted with pyBKT (decision/bkt_fit.py, proposal section 3.2) and read from
decision/bkt_params.json. Without that file the design values below are used.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

# design values (used when no fitted parameters exist)
P_INIT, P_LEARN, P_SLIP = 0.3, 0.12, 0.10
GUESS = {"PROBE": 0.15, "HUMAN_FIRST": 0.20, "HINT": 0.45, "GUIDED": 0.60, "SHARED": 0.80, "EMERGENCY": 1.0}
SLIP = {"PROBE": 0.2}  # a short unaided check: allow more room for a slip than for a full task
LEARN: dict[str, float] = {}  # per tier when fitted; otherwise P_LEARN x (1 - guess)
PRIOR_BY_LEVEL: dict[str, float] = {}
SOURCE = "design values"

PARAMS_FILE = Path(__file__).with_name("bkt_params.json")


def _load() -> None:
    global P_INIT, SOURCE
    try:
        p = json.loads(PARAMS_FILE.read_text())
    except (OSError, ValueError):
        return
    for t, v in p.get("guess", {}).items():
        GUESS[t] = float(v)
    GUESS["EMERGENCY"] = 1.0  # design rule, not a fitted value: an AI-written answer is never evidence
    for t, v in p.get("slip", {}).items():
        SLIP[t] = float(v)
    for t, v in p.get("learn", {}).items():
        LEARN[t] = max(0.005, float(v))
    PRIOR_BY_LEVEL.update({k: float(v) for k, v in p.get("prior_by_level", {}).items()})
    if PRIOR_BY_LEVEL:
        P_INIT = round(sum(PRIOR_BY_LEVEL.values()) / len(PRIOR_BY_LEVEL), 3)
    SOURCE = f"fitted with pyBKT on {p.get('source', 'attempt log')} ({p.get('attempts', '?')} attempts)"


_load()


def prior_for(difficulty: int | None) -> float:
    """Starting mastery for a brand-new skill, by task difficulty (1-2 easy, 3 medium, 4-5 hard)."""
    if difficulty is None or not PRIOR_BY_LEVEL:
        return P_INIT
    level = "easy" if difficulty <= 2 else "medium" if difficulty == 3 else "hard"
    return PRIOR_BY_LEVEL.get(level, P_INIT)


@dataclass
class BKTUpdate:
    before: float
    after: float
    evidence: str


def update(p: float | None, tier: str, success: bool) -> BKTUpdate:
    p0 = P_INIT if p is None else p
    g = GUESS[tier]
    slip = SLIP.get(tier, P_SLIP)
    if success:
        if g >= 1.0:
            return BKTUpdate(p0, p0, "no evidence: the AI produced the solution")
        post = p0 * (1 - slip) / (p0 * (1 - slip) + (1 - p0) * g)
    else:
        post = p0 * slip / (p0 * slip + (1 - p0) * (1 - g))
    # learning can happen while working, more when the student did more of the work
    if g >= 1.0:
        learn = 0.0
    else:
        learn = LEARN.get(tier, P_LEARN * (1 - g))
    after = post + (1 - post) * learn
    kind = "unaided success" if success and g <= 0.2 else "assisted success" if success else "failure"
    return BKTUpdate(round(p0, 4), round(min(0.99, max(0.01, after)), 4), kind)
