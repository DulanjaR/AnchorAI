"""Overload check for a normal day (methodology update, 14 Oct 2026).

Separate from the MVD path: it does not place anything and changes no plan. It
answers "does the planned work fit today?" before any disruption, using the
corrected durations from ML Model 1 (or the plain estimates while drift = 1.0).

PROPOSED scope (DECISIONS.md 2026-10-14, docs/METHODOLOGY.md §2.1):
  available minutes = work hours from planFrom, minus protected blocks
  planned minutes   = sum of the tasks' point durations (also with 'high')
  slack ratio       = (available − planned) ÷ available
  early deadline warning: tasks due on the plan day (or overdue), in deadline
    order; a task is flagged when the free time before its deadline is less than
    its minutes plus those of every earlier-deadline task.
"""
from types import ModuleType
from typing import Any, Mapping, TypedDict

from components.c1_disruption.engine import config as default_config
from components.c1_disruption.engine.jsnum import js_round
from components.c1_disruption.engine.mvd import build_free_gaps, check_duration_range
from components.c1_disruption.engine.time import (
    MINUTES_PER_HOUR,
    Interval,
    calendar_days_between,
    parse_date_time,
    to_minutes,
)


class DeadlineWarning(TypedDict):
    taskId: str
    deadline: str
    neededMinutes: int  # this task + every earlier-deadline task due today
    availableMinutes: int  # free minutes before the deadline


class OverloadReport(TypedDict):
    availableMinutes: int
    plannedMinutes: int
    plannedMinutesHigh: int
    slackRatio: float | None  # None when no time is available at all
    slackRatioHigh: float | None
    overloaded: bool
    overloadedHigh: bool
    deadlineWarnings: list[DeadlineWarning]


def _minutes(hours: float) -> int:
    return js_round(hours * MINUTES_PER_HOUR)


def _slack(available: int, planned: int) -> float | None:
    return (available - planned) / available if available > 0 else None


def _free_before(gaps: list[Interval], limit: int) -> int:
    return sum(max(0, min(g.end, limit) - g.start) for g in gaps)


def check_overload(input: Mapping[str, Any], config: ModuleType = default_config) -> OverloadReport:
    """`input` has the MVD input shape without a disruption: date, workHours,
    planFrom (optional), protectedBlocks, tasks (estimatedHours = corrected point,
    estimatedHoursHigh optional)."""
    date = input["date"]
    work = input["workHours"]
    plan_from = input.get("planFrom") or work["start"]
    tasks = input.get("tasks") or []
    for task in tasks:
        check_duration_range(task)

    horizon = Interval(max(to_minutes(work["start"]), to_minutes(plan_from)), to_minutes(work["end"]))
    gaps = build_free_gaps(horizon, input.get("protectedBlocks") or [])
    available = sum(g.end - g.start for g in gaps)

    def high_hours(task: Mapping[str, Any]) -> float:
        return task["estimatedHours"] if task.get("estimatedHoursHigh") is None else task["estimatedHoursHigh"]

    planned = sum(_minutes(t["estimatedHours"]) for t in tasks)
    planned_high = sum(_minutes(high_hours(t)) for t in tasks)

    # Early deadline warning: tasks due on the plan day (or overdue), earliest first.
    due = sorted(
        (t for t in tasks if calendar_days_between(date, t["deadline"]) <= 0),
        key=lambda t: (parse_date_time(t["deadline"]), _minutes(t["estimatedHours"])),
    )
    warnings: list[DeadlineWarning] = []
    needed = 0
    for task in due:
        needed += _minutes(task["estimatedHours"])
        overdue = calendar_days_between(date, task["deadline"]) < 0
        deadline_time = 0 if overdue else to_minutes(task["deadline"].partition("T")[2][:5] or "23:59")
        free = _free_before(gaps, deadline_time)
        if free < needed:
            warnings.append({
                "taskId": task["id"], "deadline": task["deadline"], "neededMinutes": needed, "availableMinutes": free,
            })

    return {
        "availableMinutes": available,
        "plannedMinutes": planned,
        "plannedMinutesHigh": planned_high,
        "slackRatio": _slack(available, planned),
        "slackRatioHigh": _slack(available, planned_high),
        "overloaded": planned > available,
        "overloadedHigh": planned_high > available,
        "deadlineWarnings": warnings,
    }
