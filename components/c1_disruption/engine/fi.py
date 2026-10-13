"""Task Flexibility Index (CLAUDE.md §3.1). Pure functions only.

  Fi = (Deadline Proximity × Priority Score) / (Duration × Environmental Feasibility)

Low Fi = urgent, keep. High Fi = flexible, safe to move or reduce.

`config` is the engine config module (engine/config.py) by default; tests may
pass any object with the same attributes.
"""
from types import ModuleType

from components.c1_disruption.engine import config as default_config
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.time import calendar_days_between


def lookup_ef(disruption_type: str, task_type: str, config: ModuleType = default_config) -> float:
    """EF of a task type under a disruption, straight from the config.

    A None value is an open research decision for the owner (CLAUDE.md §4), so we
    stop with an error that names the missing pair instead of guessing a value.
    """
    row = config.ENV_FEASIBILITY.get(disruption_type)
    if row is None:
        raise EngineError(
            f"Unknown disruption type '{disruption_type}' (not in engine/config.py ENV_FEASIBILITY)"
        )
    if task_type not in row:
        raise EngineError(
            f"Unknown task type '{task_type}' for disruption '{disruption_type}' "
            "(not in engine/config.py ENV_FEASIBILITY)"
        )
    ef = row[task_type]
    if ef is None:
        # Golden S11 message (config path changed from config.js, DECISIONS.md 2026-10-13).
        raise EngineError(
            f"EF not defined for disruption '{disruption_type}' and task type '{task_type}' "
            "(null in engine/config.py; open research decision for the owner)"
        )
    return ef


def disruption_kind(disruption_type: str, config: ModuleType = default_config) -> str:
    """'environment' or 'unavailable' (Task 2a). Unknown types are an error."""
    kind = config.DISRUPTION_KINDS.get(disruption_type)
    if kind is None:
        raise EngineError(
            f"Unknown disruption type '{disruption_type}' (not in engine/config.py DISRUPTION_KINDS)"
        )
    return kind


def is_blocked_by_disruption(disruption_ef: float, config: ModuleType = default_config) -> bool:
    """Feasibility gate: below the gate the task is physically impossible DURING the
    disruption window, so it may only be placed outside it."""
    return disruption_ef < config.FEASIBILITY_GATE


def ef_for_fi(disruption_ef: float, window_active: bool, config: ModuleType = default_config) -> float:
    """EF that goes into Fi = EF of the slot the task is expected to run in.

    Fi is computed ONCE, before placement (decision Q5, 6 Oct 2026):
      - blocked task (EF < gate) → can only run outside the window → normal EF (1.0)
      - window still ahead in today's plan → task is expected to run in it → disruption EF
      - window already over → normal EF (1.0)
    """
    if is_blocked_by_disruption(disruption_ef, config):
        return config.OUTSIDE_WINDOW_EF
    return disruption_ef if window_active else config.OUTSIDE_WINDOW_EF


def deadline_proximity(plan_date: str, deadline: str, config: ModuleType = default_config) -> float:
    """Calendar days until the deadline, floored so that "due today" (and overdue)
    is 0.5 and Fi never becomes 0."""
    return max(calendar_days_between(plan_date, deadline), config.DEADLINE_MIN_DAYS)


def _positive_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def compute_fi(
    *, deadline_days: float, priority: str, hours: float, ef: float, config: ModuleType = default_config
) -> float:
    priority_score = config.PRIORITY_SCORE.get(priority)
    if priority_score is None:
        raise EngineError(f"Unknown priority '{priority}'")
    if not _positive_number(hours):
        raise EngineError(f"Duration must be positive, got {hours} hours")
    if not _positive_number(ef):
        raise EngineError(f"EF must be positive, got {ef}")
    # Same order of operations as the Node engine, so the floats are identical.
    return (deadline_days * priority_score) / (hours * ef)
