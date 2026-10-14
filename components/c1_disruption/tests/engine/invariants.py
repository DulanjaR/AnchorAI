"""Hard rules that EVERY generated MVD must satisfy, whatever the input.

Used by the golden scenarios, the random stress test and (Phase 4) the API golden
flows. Port of the Node project's tests/helpers/invariants.js.
"""
from types import ModuleType
from typing import Any, Mapping

from components.c1_disruption.engine import config as default_config
from components.c1_disruption.engine.fi import lookup_ef
from components.c1_disruption.engine.strategy import read_strategy
from components.c1_disruption.engine.time import (
    Interval,
    block_to_intervals,
    overlaps,
    to_minutes,
    window_to_interval,
)


def _placed_slots(mvd: Mapping[str, Any]) -> list[tuple[str, Interval]]:
    return [
        (t["id"], Interval(to_minutes(t["start"]), to_minutes(t["end"])))
        for t in mvd["tasks"]
        if t["start"] is not None
    ]


def compute_ptvr(mvd: Mapping[str, Any], input: Mapping[str, Any]) -> float:
    """PTVR (Protected Time Violation Rate) = placed tasks overlapping a protected
    block ÷ placed tasks. CLAUDE.md §3.3 step 1: must be exactly 0."""
    slots = _placed_slots(mvd)
    if not slots:
        return 0
    blocks = [iv for b in input.get("protectedBlocks") or [] for iv in block_to_intervals(b)]
    violations = sum(1 for _, s in slots if any(overlaps(s, b) for b in blocks))
    return violations / len(slots)


def find_violations(
    mvd: Mapping[str, Any], input: Mapping[str, Any], config: ModuleType = default_config
) -> list[str]:
    """Returns a list of broken rules (empty = all good), so a failing test shows
    every problem at once."""
    problems: list[str] = []
    slots = _placed_slots(mvd)

    ptvr = compute_ptvr(mvd, input)
    if ptvr != 0:
        problems.append(f"PTVR is {ptvr}, must be 0")

    for i, (id_a, a) in enumerate(slots):
        for id_b, b in slots[i + 1:]:
            if overlaps(a, b):
                problems.append(f"{id_a} overlaps {id_b}")

    work = input["workHours"]
    horizon_start = max(to_minutes(work["start"]), to_minutes(input.get("planFrom") or work["start"]))
    horizon_end = to_minutes(work["end"])
    for task_id, s in slots:
        if s.start < horizon_start or s.end > horizon_end:
            problems.append(f"{task_id} is outside the planning horizon")

    max_pct = read_strategy(input.get("strategy"), config).compress_ratio * 100  # default 50
    window = window_to_interval(input["disruption"])  # same clipping as the engine
    unavailable = config.DISRUPTION_KINDS[input["disruption"]["type"]] == "unavailable"
    for t in mvd["tasks"]:
        if t["start"] is not None:
            slot = Interval(to_minutes(t["start"]), to_minutes(t["end"]))
            if unavailable:
                # Task 2a: an "unavailable" window is taken time; nothing may be placed in it.
                if overlaps(slot, window):
                    problems.append(f"{t['id']} is placed inside an unavailable window")
            else:
                ef = lookup_ef(input["disruption"]["type"], t["type"], config)
                if ef < config.FEASIBILITY_GATE and overlaps(slot, window):
                    problems.append(f"{t['id']} (EF {ef}) is placed inside the disruption window")
            if not 0 <= t["compressionPct"] <= max_pct:
                problems.append(f"{t['id']} compression {t['compressionPct']}% is outside 0–{max_pct}%")
        if not isinstance(t["explanation"], str) or not t["explanation"]:
            problems.append(f"{t['id']} has no explanation")

    if len(mvd["tasks"]) != len(input.get("tasks") or []):
        problems.append("not every input task appears in the MVD")
    if len(mvd["protect"]) != len(input.get("protectedBlocks") or []):
        problems.append("not every protected block is returned")
    return problems
