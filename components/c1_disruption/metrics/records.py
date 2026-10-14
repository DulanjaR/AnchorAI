"""Reads what the metrics need from the stored records (repository), for the pilot
analysis. Simulation output uses the same shapes, so both go through plan_metrics."""
from typing import Any

from components.c1_disruption.app.data.repository import Record, Repository


def task_outcomes(store: Repository, mvd: Record) -> tuple[dict[str, str], dict[str, int | None]]:
    """For the tasks of one MVD: taskId → outcome, and taskId → actual minutes,
    from the completions of that day (Mark Done buttons or end-of-day review)."""
    task_ids = {t["id"] for t in mvd["plan"]["tasks"]}
    outcomes: dict[str, str] = {}
    actual: dict[str, int | None] = {}
    for c in store.list("completions", {"userId": mvd["userId"], "date": mvd["date"]}):
        if c["taskId"] in task_ids:
            outcomes[c["taskId"]] = c["outcome"]
            actual[c["taskId"]] = c["actualMinutes"]
    return outcomes, actual


def decided_feedback(store: Repository, user_id: str | None = None) -> list[dict[str, Any]]:
    """Feedback records (one per decided MVD), optionally for one user."""
    return store.list("feedback", {"userId": user_id} if user_id else None)
