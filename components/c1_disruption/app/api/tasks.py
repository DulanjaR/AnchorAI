"""Tasks: CRUD plus the Start Task / Mark Done buttons (primary completion
detection, CLAUDE.md §3.5). Overruns are only recorded, never cascaded."""
from fastapi import APIRouter, Depends, Query, Response

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.errors import bad_request, conflict
from components.c1_disruption.app.api.models import NewTask, TaskBody
from components.c1_disruption.app.api.validation import require_date
from components.c1_disruption.app.data.repository import Record
from components.c1_disruption.app.services.clock import iso_utc, parse_iso
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.owned import load_owned
from components.c1_disruption.engine.jsnum import js_round
from components.c1_disruption.engine.time import to_minutes

router = APIRouter(prefix="/tasks")

USER_FIELDS = ("title", "type", "priority", "estimatedHours", "deadline", "delegable", "plannedDate",
               "plannedStart", "plannedEnd")


def _task_fields(body: TaskBody, current: Record | None = None) -> Record:
    """The user-settable fields after a POST (current = None: defaults apply) or
    a PATCH (missing fields keep their current values)."""
    sent = body.model_dump()
    category = sent.pop("category")
    if current is None:
        task = {**sent, "delegable": sent["delegable"] if sent["delegable"] is not None else False}
    else:
        task = {name: sent[name] if sent[name] is not None else current[name] for name in USER_FIELDS}
        category = category if category is not None else current.get("category")
    if category is not None:  # optional (ML Model 1 only): stored only when set
        task["category"] = category
    if (task["plannedStart"] is None) != (task["plannedEnd"] is None):
        raise bad_request("'plannedStart' and 'plannedEnd' must be given together")
    if task["plannedStart"] is not None and to_minutes(task["plannedEnd"]) <= to_minutes(task["plannedStart"]):
        raise bad_request("'plannedEnd' must be after 'plannedStart'")
    return task


@router.get("")
def list_tasks(
    date: str | None = Query(default=None), user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)
) -> list[dict]:
    where = {"userId": user_id}
    if date is not None:
        where["plannedDate"] = require_date(date, "date")
    return deps.store.list("tasks", where)


@router.post("", status_code=201)
def create_task(body: NewTask, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    task = {
        "userId": user_id,
        **_task_fields(body),
        "status": "planned",
        "startedAt": None,
        "doneAt": None,
        "mvdTag": None,
        "mvdStart": None,
        "mvdEnd": None,
        "mvdId": None,
    }
    return deps.store.create("tasks", task)


@router.get("/{task_id}")
def get_task(task_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return load_owned(deps.store, "tasks", task_id, user_id, "Task")


@router.patch("/{task_id}")
def change_task(
    task_id: str, body: TaskBody, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)
) -> dict:
    current = load_owned(deps.store, "tasks", task_id, user_id, "Task")
    return deps.store.update("tasks", current["id"], _task_fields(body, current))


@router.delete("/{task_id}", status_code=204)
def delete_task(task_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> Response:
    load_owned(deps.store, "tasks", task_id, user_id, "Task")
    deps.store.remove("tasks", task_id)
    return Response(status_code=204)


@router.post("/{task_id}/start")
def start_task(task_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    """Start Task button. The app cancels its +15/+30 min reminders when this succeeds."""
    task = load_owned(deps.store, "tasks", task_id, user_id, "Task")
    if task["status"] == "done":
        raise conflict("Task is already done")
    if task["startedAt"]:
        raise conflict("Task is already started")
    return deps.store.update("tasks", task["id"], {"status": "in_progress", "startedAt": iso_utc(deps.clock.now())})


@router.post("/{task_id}/done")
def finish_task(task_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    """Mark Done button. actualMinutes needs a start time; without one it is None
    (the task still counts as done)."""
    task = load_owned(deps.store, "tasks", task_id, user_id, "Task")
    if task["status"] == "done":
        raise conflict("Task is already done")
    done_at = deps.clock.now()
    actual_minutes = (
        js_round((done_at - parse_iso(task["startedAt"])).total_seconds() / 60) if task["startedAt"] else None
    )
    deps.store.create("completions", {
        "userId": user_id,
        "taskId": task["id"],
        "date": task["plannedDate"],
        "source": "buttons",
        "outcome": "done",
        "partialPct": None,
        "actualMinutes": actual_minutes,
        "estimatedMinutes": js_round(task["estimatedHours"] * 60),
    })
    return deps.store.update("tasks", task["id"], {"status": "done", "doneAt": iso_utc(done_at)})
