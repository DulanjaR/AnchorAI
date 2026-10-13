"""Classification rules (CLAUDE.md §3.2–3.3). Pure functions only.

Tasks are split into placement groups by Fi, placed group by group, and then
tagged by OUTCOME (decision Q2): what actually happened to the task decides its
tag, not just the group it started in.
"""
from types import ModuleType
from typing import Protocol

from components.c1_disruption.engine import config as default_config

# Fi values are floats; two tasks with the "same" Fi can differ in the last bit
# (e.g. 1.0/0.7 computed two ways). This tolerance treats them as a tie so the
# deadline/duration tie-breaks apply. It is a numeric tolerance, not a tunable.
FI_TIE_TOLERANCE = 1e-9

# Placement groups, in placement order:
#   A  Fi < Keep threshold AND High priority       → Keep candidates (step 5)
#   B  Fi < Keep threshold AND not High            → Reduce candidates, placed first (step 6a)
#   C  Keep threshold ≤ Fi ≤ top of Reduce range   → Reduce candidates (step 7)
#   D  Fi above the Reduce range                   → never placed today (step 8)
GROUPS = ("A", "B", "C", "D")


class Orderable(Protocol):
    group: str
    fi: float
    deadline_key: int
    duration_minutes: int


def group_for(fi: float, priority: str, config: ModuleType = default_config) -> str:
    if fi < config.KEEP_THRESHOLD:
        return "A" if priority == "High" else "B"
    if fi <= config.REDUCE_RANGE[1]:
        return "C"
    return "D"


def compare_placement_order(a: Orderable, b: Orderable) -> float:
    """Placement order (step 4 and Q4), for functools.cmp_to_key.

    Group, then Fi ascending (most urgent first), ties → earliest absolute
    deadline, then shortest duration. Because tasks are placed one by one in this
    order, the LAST task is the one that gets reduced when time runs out (step 6).
    """
    if a.group != b.group:
        return GROUPS.index(a.group) - GROUPS.index(b.group)
    if abs(a.fi - b.fi) > FI_TIE_TOLERANCE:
        return a.fi - b.fi
    if a.deadline_key != b.deadline_key:
        return a.deadline_key - b.deadline_key
    return a.duration_minutes - b.duration_minutes


def tag_for(*, placed: bool, compressed: bool, delegable: bool) -> str:
    """Tag by outcome (Q2, Q3): placed in full → Keep; placed shorter → Reduce;
    not placed → Delegate if the user flagged it delegable, otherwise Move."""
    if placed:
        return "Reduce" if compressed else "Keep"
    return "Delegate" if delegable else "Move"


def reason_for(
    *, placed: bool, compressed: bool, blocked: bool, group: str, delegable: bool, time_taken: bool = False
) -> str:
    """One reason code per task; the first matching rule wins.

    `time_taken` = the disruption is of kind "unavailable" (Task 2a): an unplaced
    task did not fit because that time went to the disruption.
    """
    if placed:
        if compressed:
            return "REDUCE_BUDGET"
        if blocked:
            return "OUTSIDE_DISRUPTION_WINDOW"
        return "KEEP_URGENT" if group == "A" else "FITS_FULLY"
    if delegable:
        return "DELEGABLE"
    if blocked:
        return "BLOCKED_BY_DISRUPTION"
    if group == "D":
        return "LOW_URGENCY"
    if time_taken:
        return "TIME_TAKEN_BY_DISRUPTION"
    return "BUDGET_EXCEEDED"


def has_deadline_risk(
    *, tag: str, days_until_deadline: int, fi: float, config: ModuleType = default_config
) -> bool:
    """Deadline risk warning (step 9, revised 6 Oct 2026): the task was moved off
    today although it is due today or tomorrow, or is urgent (Fi below the Keep
    threshold). The planner cannot create time, so it makes the trade-off visible."""
    return tag == "Move" and (days_until_deadline <= config.DEADLINE_RISK_DAYS or fi < config.KEEP_THRESHOLD)
