"""Model 2 actions = concrete strategy configs for the engine (engine/strategy.py),
and the distinctness check (docs/METHODOLOGY.md §4).

Until defer order and recovery timing are defined by the owner, actions differ in
compress ratio only. The first action is the approved default behaviour.
"""
from itertools import combinations
from typing import Any, Iterable, Mapping

from components.c1_disruption.app.services.planning import STRATEGIES
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.mvd import generate_mvd

ACTIONS: dict[str, dict[str, Any]] = STRATEGIES  # one catalogue for the service and the bandit


def _signature(mvd: Mapping[str, Any]) -> tuple:
    """What the student sees: every task's tag and slot."""
    return tuple((t["id"], t["tag"], t["start"], t["end"]) for t in mvd["tasks"])


def distinctness(inputs: Iterable[Mapping[str, Any]], actions: Mapping[str, Mapping[str, Any]] = ACTIONS) -> dict[str, Any]:
    """For each pair of actions: share of scenarios where their MVDs differ (any tag
    or slot). Scenarios the engine cannot plan (e.g. a None EF) are skipped.

    Returns {"pairs": {(a, b): share}, "scenarios": n, "neverDiffer": [(a, b), ...]};
    pairs that never differ are candidates to merge or drop.
    """
    signatures: list[dict[str, tuple]] = []
    for data in inputs:
        try:
            signatures.append({a: _signature(generate_mvd({**data, "strategy": dict(cfg)})) for a, cfg in actions.items()})
        except EngineError:
            continue
    n = len(signatures)
    pairs = {
        (a, b): (sum(s[a] != s[b] for s in signatures) / n if n else 0.0)
        for a, b in combinations(actions, 2)
    }
    return {"pairs": pairs, "scenarios": n, "neverDiffer": [p for p, share in pairs.items() if share == 0]}
