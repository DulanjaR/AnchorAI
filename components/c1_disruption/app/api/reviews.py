"""End-of-day review: the backup completion detection (CLAUDE.md §3.5). The app
shows it at the user's own work-end time; the API only stores the answers."""
from fastapi import APIRouter, Depends

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.errors import bad_request, conflict
from components.c1_disruption.app.api.models import ReviewBody
from components.c1_disruption.app.api.validation import require_date
from components.c1_disruption.app.data.repository import Record, Repository
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.engine.jsnum import js_round

router = APIRouter(prefix="/reviews")


def _tasks_without_completion(store: Repository, user_id: str, date: str) -> list[Record]:
    tasks = store.list("tasks", {"userId": user_id, "plannedDate": date})
    completed = {c["taskId"] for c in store.list("completions", {"userId": user_id, "date": date})}
    return [t for t in tasks if t["id"] not in completed]


@router.get("/{date}")
def open_tasks(date: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> list[dict]:
    return _tasks_without_completion(deps.store, user_id, require_date(date, "date"))


@router.post("/{date}", status_code=201)
def review(
    date: str, body: ReviewBody, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)
) -> list[dict]:
    date = require_date(date, "date")
    # Check every item first, then write, so a bad item never leaves half a review.
    open_by_id = {t["id"]: t for t in _tasks_without_completion(deps.store, user_id, date)}
    seen: set[str] = set()
    answers = []
    for item in body.items:
        task_id = item.taskId
        if task_id in seen:
            raise bad_request(f"Task '{task_id}' appears twice")
        seen.add(task_id)
        task = open_by_id.get(task_id)
        if task is None:
            raise conflict(f"Task '{task_id}' is not open for review on {date} (unknown, or already completed)")
        if item.outcome == "partial" and item.partialPct is None:
            raise bad_request("'partialPct' is required (one of: 25, 50, 75)")
        if item.outcome != "partial" and "partialPct" in item.model_fields_set:
            raise bad_request(f"'partialPct' is only allowed when outcome is 'partial' (task '{task_id}')")
        if item.actualMinutes is not None and item.outcome == "not_done":
            raise bad_request(f"'actualMinutes' is not allowed when outcome is 'not_done' (task '{task_id}')")
        answers.append((task, item.outcome, item.partialPct if item.outcome == "partial" else None, item.actualMinutes))

    created = []
    for task, outcome, partial_pct, minutes in answers:
        created.append(deps.store.create("completions", {
            "userId": user_id,
            "taskId": task["id"],
            "date": date,
            "source": "review",
            "outcome": outcome,
            "partialPct": partial_pct,
            "actualMinutes": minutes,  # optional in the review (no timestamps); None if not given
            "estimatedMinutes": js_round(task["estimatedHours"] * 60),
        }))
        deps.store.update("tasks", task["id"], {"status": outcome})
    return created
