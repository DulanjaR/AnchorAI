"""Minimum Viable Day generator (CLAUDE.md §3.3).

Pure: plain input in, plain dict out. No database, HTTP or clock access; the plan
date and the time the replan starts (planFrom) come in as input, so the same
input always gives the same MVD. Input and output shapes: engine/schema.py.

estimatedHours is the duration AFTER drift correction (ML Model 1). Until Task 4
exists, callers pass the plain estimate (drift = 1.0).
"""
from dataclasses import dataclass
from functools import cmp_to_key
from types import ModuleType

from components.c1_disruption.engine import config as default_config
from components.c1_disruption.engine.classify import (
    compare_placement_order,
    group_for,
    has_deadline_risk,
    reason_for,
    tag_for,
)
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.explain import ExplainContext, explain_protected, explain_task
from components.c1_disruption.engine.fi import (
    compute_fi,
    deadline_proximity,
    disruption_kind,
    ef_for_fi,
    is_blocked_by_disruption,
    lookup_ef,
)
from components.c1_disruption.engine.jsnum import js_round
from components.c1_disruption.engine.schema import Mvd, MvdInput, MvdTask, ProtectedBlock, TaskInput
from components.c1_disruption.engine.strategy import Strategy, read_strategy
from components.c1_disruption.engine.time import (
    MINUTES_PER_HOUR,
    Interval,
    block_to_intervals,
    calendar_days_between,
    overlaps,
    parse_date_time,
    subtract_interval,
    to_hhmm,
    to_minutes,
    window_to_interval,
)


def _length(iv: Interval) -> int:
    return iv.end - iv.start


@dataclass(frozen=True)
class _Context:
    date: str
    disruption_type: str
    window_active: bool
    unavailable: bool


@dataclass(frozen=True)
class ScoredTask:
    """One task with everything placement needs (steps 3–4)."""

    task: TaskInput
    blocked: bool
    ef_used: float
    fi: float
    group: str
    days_until_deadline: int
    deadline_key: int
    duration_minutes: int


def build_free_gaps(horizon: Interval, protected_blocks: list[ProtectedBlock]) -> list[Interval]:
    """Steps 1–2: free time = planning horizon minus protected blocks, as a sorted
    list of intervals. The horizon starts at the later of work start and planFrom,
    because time that has already passed cannot be planned."""
    gaps = [horizon] if horizon.start < horizon.end else []
    for block in protected_blocks:
        for piece in block_to_intervals(block):
            gaps = subtract_interval(gaps, piece)
    return gaps


def _feasibility_for(task: TaskInput, ctx: _Context, config: ModuleType) -> tuple[bool, float]:
    """EF and gate for one task → (blocked, efUsed).

    environment kind: EF from config. The lookup runs for every task, so a None
      EF always raises, even if Fi would end up using 1.0.
    unavailable kind (Task 2a): no lookup. The window is not free time at all, so
      every task runs outside it, in normal conditions (EF 1.0); nothing is gated.
    """
    if ctx.unavailable:
        if task["type"] not in config.TASK_TYPES:
            raise EngineError(f"Unknown task type '{task['type']}' (not in engine/config.py TASK_TYPES)")
        return False, config.OUTSIDE_WINDOW_EF
    disruption_ef = lookup_ef(ctx.disruption_type, task["type"], config)
    return (
        is_blocked_by_disruption(disruption_ef, config),
        ef_for_fi(disruption_ef, ctx.window_active, config),
    )


def check_duration_range(task: TaskInput) -> None:
    """Optional duration range from ML Model 1: low ≤ point ≤ high (hours).

    Fi and placement use the point value (estimatedHours). The range is checked
    here so a bad range is caught early; how 'high' is used is pending owner
    definition (methodology update, 14 Oct 2026).
    """
    point = task["estimatedHours"]
    for key in ("estimatedHoursLow", "estimatedHoursHigh"):
        value = task.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0):
            raise EngineError(f"Task '{task['id']}': '{key}' must be a positive number, got {value!r}")
    low = point if task.get("estimatedHoursLow") is None else task["estimatedHoursLow"]
    high = point if task.get("estimatedHoursHigh") is None else task["estimatedHoursHigh"]
    if not low <= point <= high:
        raise EngineError(
            f"Task '{task['id']}': duration range must satisfy low ≤ estimatedHours ≤ high, got {low} / {point} / {high}"
        )


def _score_task(task: TaskInput, ctx: _Context, config: ModuleType) -> ScoredTask:
    """Steps 3–4: EF, Fi and placement group for one task."""
    blocked, ef_used = _feasibility_for(task, ctx, config)
    check_duration_range(task)
    fi = compute_fi(
        deadline_days=deadline_proximity(ctx.date, task["deadline"], config),
        priority=task["priority"],
        hours=task["estimatedHours"],
        ef=ef_used,
        config=config,
    )
    return ScoredTask(
        task=task,
        blocked=blocked,
        ef_used=ef_used,
        fi=fi,
        group=group_for(fi, task["priority"], config),
        days_until_deadline=calendar_days_between(ctx.date, task["deadline"]),
        deadline_key=parse_date_time(task["deadline"]),
        duration_minutes=js_round(task["estimatedHours"] * MINUTES_PER_HOUR),
    )


def find_slot(
    item: ScoredTask,
    gaps: list[Interval],
    window: Interval,
    window_first: bool,
    config: ModuleType = default_config,
    max_compression: float | None = None,
) -> Interval | None:
    """Finds a slot for one task in the remaining free gaps, or returns None.

    A task always gets ONE contiguous slot; it is never split across a protected
    block or across two gaps. `window_first` is False for an "unavailable"
    disruption: its window has already been removed from the gaps.
    `max_compression` comes from the strategy (default config.MAX_COMPRESSION).
    """
    if max_compression is None:
        max_compression = config.MAX_COMPRESSION
    # Feasibility gate (step 3): a blocked task may only use time outside the window.
    feasible = subtract_interval(gaps, window) if item.blocked else gaps
    need = item.duration_minutes

    # Window first (Q6, revised 6 Oct 2026): a task that CAN run during the
    # disruption goes there first, which keeps normal-condition time free for
    # tasks that need it.
    if not item.blocked and window_first:
        # a) Wholly inside the window, starting at max(gap start, window start).
        for g in feasible:
            start = max(g.start, window.start)
            if start + need <= min(g.end, window.end):
                return Interval(start, start + need)
        # b) Too long for the window: a gap that overlaps it, from the gap start.
        for g in feasible:
            if overlaps(g, window) and _length(g) >= need:
                return Interval(g.start, g.start + need)

    # Otherwise the earliest gap that holds the full task.
    for g in feasible:
        if _length(g) >= need:
            return Interval(g.start, g.start + need)

    # Reduce: use the largest gap (least compression = "only as much as needed";
    # on a tie the earliest gap wins), as long as compression stays within the max.
    largest: Interval | None = None
    for g in feasible:
        if largest is None or _length(g) > _length(largest):
            largest = g
    if largest is not None and _length(largest) >= need * (1 - max_compression):
        return largest
    return None  # cannot fit even at maximum compression


def generate_mvd(input: MvdInput, config: ModuleType = default_config) -> Mvd:
    """Builds the MVD. `input["strategy"]` is optional (engine/strategy.py); without
    it every setting is the approved default and the output is the golden one."""
    strategy: Strategy = read_strategy(input.get("strategy"), config)
    date = input["date"]
    work_hours = input["workHours"]
    disruption = input["disruption"]
    protected_blocks = input.get("protectedBlocks") or []
    tasks = input.get("tasks") or []
    plan_from = input.get("planFrom") or work_hours["start"]

    horizon = Interval(
        max(to_minutes(work_hours["start"]), to_minutes(plan_from)),
        to_minutes(work_hours["end"]),
    )
    # Clipped at the end of the plan day if it crosses midnight (see time.py).
    window = window_to_interval(disruption)
    # The window only matters if part of it is still ahead in today's plan.
    window_active = horizon.start < horizon.end and overlaps(window, horizon)

    kind = disruption_kind(disruption["type"], config)
    unavailable = kind == "unavailable"

    ctx = _Context(date, disruption["type"], window_active, unavailable)
    scored = [_score_task(task, ctx, config) for task in tasks]

    # Steps 5–7: place groups A, B, C in order; group D is never placed (step 8).
    order = sorted(scored, key=cmp_to_key(compare_placement_order))
    gaps = build_free_gaps(horizon, protected_blocks)
    # Unavailable kind: the window is taken time, exactly like a protected block.
    if unavailable:
        gaps = subtract_interval(gaps, window)
    window_first = window_active and not unavailable
    slots: dict[str, Interval] = {}
    for item in order:
        if item.group == "D":
            continue
        slot = find_slot(item, gaps, window, window_first, config, strategy.compress_ratio)
        if slot is not None:
            slots[item.task["id"]] = slot
            gaps = subtract_interval(gaps, slot)

    # Steps 8–10: tag, reason code, deadline risk and explanation per task.
    # Free time still unused after placement (minutes left in the gaps).
    free_minutes_left = sum(_length(g) for g in gaps)
    explain_ctx: ExplainContext = {
        "disruptionType": disruption["type"],
        "windowStart": disruption["start"],
        "windowEnd": disruption["end"],
        "freeMinutesLeft": free_minutes_left,
        "maxCompression": strategy.compress_ratio,
    }
    results: list[MvdTask] = []
    for item in order:
        slot = slots.get(item.task["id"])
        placed = slot is not None
        compressed = placed and _length(slot) < item.duration_minutes
        delegable = bool(item.task.get("delegable"))
        tag = tag_for(placed=placed, compressed=compressed, delegable=delegable)
        result: MvdTask = {
            "id": item.task["id"],
            "title": item.task["title"],
            "type": item.task["type"],
            "priority": item.task["priority"],
            "deadline": item.task["deadline"],
            "daysUntilDeadline": item.days_until_deadline,
            "estimatedHours": item.task["estimatedHours"],
            "delegable": delegable,
            "efUsed": item.ef_used,
            "fi": item.fi,
            "group": item.group,
            "tag": tag,
            "start": to_hhmm(slot.start) if placed else None,
            "end": to_hhmm(slot.end) if placed else None,
            # Rounded to 1 decimal like the Node engine (Math.round, halves up).
            "compressionPct": js_round(1000 * (1 - _length(slot) / item.duration_minutes)) / 10 if placed else None,
            "reason": reason_for(
                placed=placed,
                compressed=compressed,
                blocked=item.blocked,
                group=item.group,
                delegable=delegable,
                time_taken=unavailable,
            ),
            "deadlineRisk": False,
            "explanation": "",
        }
        result["deadlineRisk"] = has_deadline_risk(
            tag=tag, days_until_deadline=item.days_until_deadline, fi=item.fi, config=config
        )
        result["explanation"] = explain_task(result, explain_ctx)
        results.append(result)

    # Step 1: protected blocks are returned untouched, every one tagged Protect.
    protect = [
        {
            "id": block["id"],
            "label": block.get("label"),
            "tag": "Protect",
            "start": block["start"],
            "end": block["end"],
            "reason": "PROTECTED_BLOCK",
            "explanation": explain_protected(block),
        }
        for block in protected_blocks
    ]

    return {
        "date": date,
        "disruption": {**disruption, "kind": kind},
        "horizon": {"start": to_hhmm(horizon.start), "end": to_hhmm(horizon.end)},
        "tasks": results,
        "protect": protect,
        "freeMinutesLeft": free_minutes_left,
        "warnings": [
            {"taskId": r["id"], "code": "DEADLINE_RISK", "message": r["explanation"]}
            for r in results
            if r["deadlineRisk"]
        ],
    }
