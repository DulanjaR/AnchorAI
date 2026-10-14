"""Plan diff (methodology update, 14 Oct 2026): which task tags differ between two
MVDs generated from the SAME input, e.g. with the drift model on vs off, or with
two strategies. Used for the decision-change rate.

Pure: plain MVD dicts in (engine output, see schema.Mvd), plain dict out.
"""
from typing import Any, Mapping, TypedDict

from components.c1_disruption.engine.errors import EngineError


class TagChange(TypedDict):
    taskId: str
    before: str  # tag in plan_a
    after: str  # tag in plan_b


class PlanDiff(TypedDict):
    changed: list[TagChange]  # in plan_a's task order
    total: int  # tasks compared
    changeRate: float  # len(changed) / total; 0.0 when there are no tasks


def diff_plans(plan_a: Mapping[str, Any], plan_b: Mapping[str, Any]) -> PlanDiff:
    """Tags that differ between two plans of the same input.

    Raises EngineError if the plans do not hold the same tasks, because then they
    were not made from the same input and a tag comparison means nothing.
    Protected blocks are always 'Protect' in both, so they are not compared.
    """
    tags_a = {t["id"]: t["tag"] for t in plan_a["tasks"]}
    tags_b = {t["id"]: t["tag"] for t in plan_b["tasks"]}
    if tags_a.keys() != tags_b.keys():
        only_a = sorted(tags_a.keys() - tags_b.keys())
        only_b = sorted(tags_b.keys() - tags_a.keys())
        raise EngineError(f"Plans do not hold the same tasks (only in first: {only_a}, only in second: {only_b})")
    changed: list[TagChange] = [
        {"taskId": task_id, "before": tag, "after": tags_b[task_id]}
        for task_id, tag in tags_a.items()
        if tags_b[task_id] != tag
    ]
    total = len(tags_a)
    return {"changed": changed, "total": total, "changeRate": len(changed) / total if total else 0.0}
