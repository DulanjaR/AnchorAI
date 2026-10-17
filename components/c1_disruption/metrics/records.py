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


def _local_hour_minute(iso: str | None) -> tuple[str, int] | None:
    if not iso:
        return None
    from components.c1_disruption.app.services.clock import parse_iso, to_local
    from components.c1_disruption.engine.time import to_minutes

    date, hhmm = to_local(parse_iso(iso))
    return date, to_minutes(hhmm)


def model1_records(store: Repository, user_id: str, dataset: str = "PILOT") -> list[dict[str, Any]]:
    """Model 1 training records from a student's finished tasks (17 Oct 2026): every
    completion with actual minutes (Start/Done buttons, or minutes given in the review).
    overlapMinutes = minutes of a confirmed disruption inside the task's start–done span,
    so ml.drift.data.clean applies the exclusion rule. dataset: what the data is (not SYNTHETIC)."""
    from components.c1_disruption.engine.time import to_minutes

    out = []
    for c in store.list("completions", {"userId": user_id}):
        if not c.get("actualMinutes"):
            continue
        task = store.get("tasks", c["taskId"]) or {}
        started, done = _local_hour_minute(task.get("startedAt")), _local_hour_minute(task.get("doneAt"))
        start_minute = started[1] if started else to_minutes(task.get("plannedStart") or "09:00")
        overlap = 0
        if started and done and started[0] == done[0]:
            for d in store.list("disruptions", {"userId": user_id, "date": started[0]}):
                s, e = to_minutes(d["start"]), to_minutes(d["start"]) + d["timeLostMinutes"]
                overlap += max(0, min(e, done[1]) - max(s, started[1]))
        out.append({
            "studentId": user_id, "taskType": task.get("type", "Analog"), "priority": task.get("priority", "Medium"),
            "estimatedMinutes": c["estimatedMinutes"], "actualMinutes": c["actualMinutes"], "date": c["date"],
            "startHour": start_minute // 60, "overlapMinutes": overlap, "category": task.get("category"),
            "outcome": c["outcome"], "source": c["source"], "taskId": c["taskId"], "dataset": dataset,
        })
    return out


def model2_decisions(store: Repository, user_id: str) -> list[dict[str, Any]]:
    """Every decision the student made (today's MVD and the week proposal), with its reward."""
    out = []
    for f in store.list("feedback", {"userId": user_id}):
        mvd = store.get("mvds", f["mvdId"]) if f.get("mvdId") else None
        out.append({
            "kind": f.get("kind", "mvd"), "action": f["action"], "reward": f.get("reward"), "at": f.get("at"),
            "strategyId": (mvd or {}).get("strategyId"), "policyMode": (mvd or {}).get("policyMode"),
            "disruptionType": ((mvd or {}).get("plan") or {}).get("disruption", {}).get("type"),
            "timeToDecisionSeconds": f.get("timeToDecisionSeconds"), "choices": f.get("choices"),
            "tagChanges": f.get("tagChanges"),
        })
    return out


COLLECTIONS = ("tasks", "protectedBlocks", "disruptions", "mvds", "rearrangements", "feedback", "completions")


def export_user(store: Repository, user_id: str) -> dict[str, Any]:
    """Everything stored for one student, plus the Model 1 records and Model 2 decisions."""
    return {
        "userId": user_id, "settings": store.get("users", user_id),
        **{name: store.list(name, {"userId": user_id}) for name in COLLECTIONS},
        "model1Records": model1_records(store, user_id), "model2Decisions": model2_decisions(store, user_id),
    }
