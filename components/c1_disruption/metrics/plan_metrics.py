"""Evaluation metrics for Component 1 (docs/METHODOLOGY.md §5). Pure functions.

Inputs are plain dicts: an MVD is the engine output (engine/schema.Mvd), outcomes
are what happened to each task (from completions), decisions come from feedback
records. A rate whose denominator is 0 is None ("not defined for this event"),
never 0, so empty events cannot pull an average down.

Definitions marked PROPOSED in METHODOLOGY.md §5 are implemented exactly as
written there.
"""
from statistics import mean, median
from types import ModuleType
from typing import Any, Iterable, Mapping

from components.c1_disruption.engine import config as engine_config
from components.c1_disruption.engine.diff import diff_plans
from components.c1_disruption.engine.jsnum import js_round
from components.c1_disruption.engine.time import MINUTES_PER_HOUR, Interval, block_to_intervals, overlaps, to_minutes
from components.c1_disruption.metrics import config as metrics_config

Task = Mapping[str, Any]
PLACED_TAGS = ("Keep", "Reduce")


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _placed(mvd: Mapping[str, Any]) -> list[Task]:
    return [t for t in mvd["tasks"] if t["tag"] in PLACED_TAGS]


def _slot_minutes(task: Task) -> int:
    return to_minutes(task["end"]) - to_minutes(task["start"])


# --- critical tasks (CTRR) -------------------------------------------------------

def is_critical(task: Task, config: ModuleType = engine_config) -> bool:
    """PROPOSED: High priority and due today or tomorrow (or overdue)."""
    return task["priority"] == "High" and task["daysUntilDeadline"] <= config.DEADLINE_RISK_DAYS


def ctrr_planned(mvd: Mapping[str, Any], config: ModuleType = engine_config) -> float | None:
    """Critical tasks placed (Keep or Reduce) in the MVD ÷ critical tasks."""
    critical = [t for t in mvd["tasks"] if is_critical(t, config)]
    return _rate(sum(t["tag"] in PLACED_TAGS for t in critical), len(critical))


def ctrr_realised(mvd: Mapping[str, Any], outcomes: Mapping[str, str], config: ModuleType = engine_config) -> float | None:
    """Critical tasks completed ('done') on the day ÷ critical tasks.

    outcomes: taskId → 'done' / 'partial' / 'not_done' (a task without an entry is not done).
    """
    critical = [t for t in mvd["tasks"] if is_critical(t, config)]
    return _rate(sum(outcomes.get(t["id"]) == "done" for t in critical), len(critical))


# --- protected time ------------------------------------------------------------------

def ptvr(mvd: Mapping[str, Any], protected_blocks: Iterable[Mapping[str, str]]) -> float:
    """Protected Time Violation Rate = placed tasks overlapping a protected block ÷
    placed tasks. Must be exactly 0 (CLAUDE.md §3.3 step 1). 0 when nothing is placed."""
    slots = [Interval(to_minutes(t["start"]), to_minutes(t["end"])) for t in mvd["tasks"] if t["start"] is not None]
    if not slots:
        return 0
    blocks = [iv for b in protected_blocks for iv in block_to_intervals(b)]
    return sum(1 for s in slots if any(overlaps(s, b) for b in blocks)) / len(slots)


# --- feasibility -------------------------------------------------------------------------

def feasibility(
    mvd: Mapping[str, Any], required_hours: Mapping[str, float], max_compression: float = engine_config.MAX_COMPRESSION
) -> float | None:
    """Placed tasks whose slot holds their required minutes after the allowed
    shortening ÷ placed tasks.

    required_hours: taskId → hours the task really needs (the raw estimate, or the
    corrected point). Comparing both for the SAME event gives raw vs corrected.
    """
    placed = _placed(mvd)
    fits = sum(
        _slot_minutes(t) >= js_round(required_hours[t["id"]] * MINUTES_PER_HOUR) * (1 - max_compression) for t in placed
    )
    return _rate(fits, len(placed))


def realised_feasibility(mvd: Mapping[str, Any], actual_minutes: Mapping[str, int | None]) -> float | None:
    """Placed tasks whose actual minutes fit in their slot ÷ placed tasks with an actual."""
    measured = [t for t in _placed(mvd) if actual_minutes.get(t["id"]) is not None]
    return _rate(sum(actual_minutes[t["id"]] <= _slot_minutes(t) for t in measured), len(measured))


def plan_completion_rate(mvd: Mapping[str, Any], outcomes: Mapping[str, str]) -> float | None:
    """Placed tasks completed ('done') ÷ placed tasks."""
    placed = _placed(mvd)
    return _rate(sum(outcomes.get(t["id"]) == "done" for t in placed), len(placed))


# --- decisions -------------------------------------------------------------------------------

def decision_change_rate(plan_model_off: Mapping[str, Any], plan_model_on: Mapping[str, Any]) -> float:
    """Tags that differ between the model-off and model-on MVD of the same event ÷ tasks."""
    return diff_plans(plan_model_off, plan_model_on)["changeRate"]


def acceptance(actions: Iterable[str]) -> dict[str, float | None]:
    """actions: 'accept' / 'edit' / 'reject' per decided MVD."""
    actions = list(actions)
    return {
        "accepted": _rate(actions.count("accept"), len(actions)),
        "acceptedOrEdited": _rate(actions.count("accept") + actions.count("edit"), len(actions)),
        "decided": len(actions),
    }


def edits_per_mvd(feedback: Iterable[Mapping[str, Any]]) -> dict[str, float | None]:
    """Tasks changed per edited MVD and per decided MVD (feedback records)."""
    feedback = list(feedback)
    edited = [len(f["edits"] or []) for f in feedback if f["action"] == "edit"]
    return {
        "perEditedMvd": mean(edited) if edited else None,
        "perDecidedMvd": sum(edited) / len(feedback) if feedback else None,
    }


def time_to_decision(seconds: Iterable[float | None]) -> dict[str, float | None]:
    values = [s for s in seconds if s is not None]
    return {"mean": mean(values) if values else None, "median": median(values) if values else None, "n": len(values)}


# --- slack -----------------------------------------------------------------------------------------

def is_tight_slack(slack_ratio: float | None, threshold: float = metrics_config.TIGHT_SLACK_THRESHOLD) -> bool:
    """Slack ratio (engine/overload.py) below the threshold; no available time counts as tight."""
    return slack_ratio is None or slack_ratio < threshold


# --- after D-MOVE (PROPOSED, not implemented) -------------------------------------------------------

def carry_over_placement_rate(*args: Any, **kwargs: Any) -> float:
    raise NotImplementedError("Carry-over metrics need D-MOVE, which is PROPOSED and not approved yet")


def post_move_deadline_misses(*args: Any, **kwargs: Any) -> int:
    raise NotImplementedError("Carry-over metrics need D-MOVE, which is PROPOSED and not approved yet")
