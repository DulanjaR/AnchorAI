"""Bayesian Knowledge Tracing per (user, skill), with a tier-dependent guess parameter.

Standard BKT updates P(mastered) from each observed outcome. The HCDE twist: a success only counts
as evidence of the student's OWN capability in proportion to how little help they had. A success
under EMERGENCY (the AI wrote the answer) says nothing about mastery, so its "guess" probability is 1
and the estimate does not move. A success with no help (HUMAN_FIRST, or a passed PROBE) is full
evidence. Failures always count. This is what stops borrowed capability from inflating the profile.
"""
from __future__ import annotations

from dataclasses import dataclass

P_INIT, P_LEARN, P_SLIP = 0.3, 0.12, 0.10
# probability of "succeeding without mastery" at each level of help
GUESS = {"PROBE": 0.15, "HUMAN_FIRST": 0.20, "HINT": 0.45, "GUIDED": 0.60, "SHARED": 0.80, "EMERGENCY": 1.0}


@dataclass
class BKTUpdate:
    before: float
    after: float
    evidence: str


def update(p: float | None, tier: str, success: bool) -> BKTUpdate:
    p0 = P_INIT if p is None else p
    g = GUESS[tier]
    if success:
        if g >= 1.0:
            return BKTUpdate(p0, p0, "no evidence: the AI produced the solution")
        post = p0 * (1 - P_SLIP) / (p0 * (1 - P_SLIP) + (1 - p0) * g)
    else:
        post = p0 * P_SLIP / (p0 * P_SLIP + (1 - p0) * (1 - g))
    # learning can happen while working, more when the student did more of the work
    learn = P_LEARN * (1 - g) if g < 1.0 else 0.0
    after = post + (1 - post) * learn
    kind = "unaided success" if success and g <= 0.2 else "assisted success" if success else "failure"
    return BKTUpdate(round(p0, 4), round(min(0.99, max(0.01, after)), 4), kind)
