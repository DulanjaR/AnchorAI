"""Business rules for C3. Routes stay thin; everything that decides something lives here."""
from __future__ import annotations

import csv
import io
import json
import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from . import models as m
from .difficulty import DEPTH, predict_difficulty
from .generators import generate_summary, template_text
from .schemas import CheckpointIn, ResumeIn
from .summary import build_summary, summary_to_text


class ServiceError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


SEED_TASKS = [
    ("Hotel booking website", "code", "moderate", "doing"),
    ("Database assignment report", "document", "moderate", "doing"),
    ("Python data-cleaning script", "code", "simple", "todo"),
    ("Software architecture quiz notes", "document", "simple", "done"),
]


# ------------------------------------------------------------------ helpers
def predict(minutes, complexity, open_items, type_) -> dict:
    p = predict_difficulty(minutes, complexity, open_items, type_)
    return {"score": p["score"], "max": p["max"], "level": p["level"], "depth": p["depth"]["name"],
            "suggested": p["depth"]["suggested"], "reasons": p["reasons"]}


def _task(db: Session, user: str, task_id: str) -> m.Task:
    task = db.get(m.Task, task_id)
    if task is None or task.user_id != user:
        raise ServiceError(404, "Task not found.")
    return task


def open_checkpoint(db: Session, task: m.Task) -> m.Checkpoint | None:
    return db.scalars(select(m.Checkpoint).where(m.Checkpoint.task_id == task.id, m.Checkpoint.resumed.is_(False))
                      .order_by(m.Checkpoint.id.desc()).limit(1)).first()


def checkpoint_out(c: m.Checkpoint) -> dict:
    return {"id": c.id, "goal": c.goal, "completed": c.completed, "workingPoint": c.working_point, "problem": c.problem,
            "nextStep": c.next_step, "resources": c.resources, "openItems": list(c.open_items or []),
            "files": list(c.files or []), "type": c.interruption_type, "minutes": c.minutes, "complexity": c.complexity,
            "level": c.level, "score": c.score, "depth": c.depth, "trigger": c.trigger, "savedAt": m.to_ms(c.created_at)}


def task_out(db: Session, t: m.Task) -> dict:
    cp = open_checkpoint(db, t) if t.status == "interrupted" else None
    return {"id": t.id, "title": t.title, "kind": t.kind, "complexity": t.complexity, "column": t.status,
            "checkpoint": checkpoint_out(cp) if cp else None}


def log_event(db: Session, user: str, event: str, task: m.Task | None = None, payload: dict | None = None,
              ts=None) -> None:
    db.add(m.EventLog(user_id=user, task_id=task.id if task else None, task_title=task.title if task else "",
                      event=event, payload=payload or {}, ts=ts or m.utcnow()))


def _cp_dict(c: m.Checkpoint) -> dict:
    return {"goal": c.goal, "completed": c.completed, "workingPoint": c.working_point, "problem": c.problem,
            "nextStep": c.next_step, "resources": c.resources, "openItems": list(c.open_items or [])}


def _away(c: m.Checkpoint, away_minutes: float | None) -> float:
    if away_minutes is not None:
        return away_minutes
    return max(0.0, (m.utcnow() - c.created_at).total_seconds() / 60)


# ------------------------------------------------------------------ tasks
def seed_if_empty(db: Session, user: str) -> None:
    if db.scalar(select(func.count()).select_from(m.Task).where(m.Task.user_id == user)):
        return
    base = m.utcnow()
    for i, (title, kind, cx, status) in enumerate(SEED_TASKS):
        db.add(m.Task(id=str(uuid.uuid4()), user_id=user, title=title, kind=kind, complexity=cx, status=status,
                      created_at=base + timedelta(milliseconds=i)))
    db.commit()


def list_tasks(db: Session, user: str) -> list[dict]:
    seed_if_empty(db, user)
    rows = db.scalars(select(m.Task).where(m.Task.user_id == user).order_by(m.Task.created_at, m.Task.id)).all()
    return [task_out(db, t) for t in rows]


def create_task(db: Session, user: str, title: str, kind: str, complexity: str) -> dict:
    seed_if_empty(db, user)
    task = m.Task(id=str(uuid.uuid4()), user_id=user, title=title, kind=kind, complexity=complexity, status="todo")
    db.add(task)
    log_event(db, user, "task_created", task, {"kind": kind, "complexity": complexity})
    db.commit()
    return task_out(db, task)


def move_task(db: Session, user: str, task_id: str, target: str) -> dict:
    task = _task(db, user, task_id)
    if task.status == target:
        return task_out(db, task)
    if target == "interrupted":
        raise ServiceError(409, "Use the checkpoint form to interrupt a task.")
    if task.status == "interrupted" and target in ("doing", "todo"):
        raise ServiceError(409, "Resume the task to continue it; it cannot be moved back." if target == "doing"
                           else "Resume or complete the task instead of moving it back.")
    origin = task.status
    task.status = target
    log_event(db, user, "task_moved", task, {"from": origin, "to": target})
    db.commit()
    return task_out(db, task)


# ------------------------------------------------------------------ checkpoint
def save_checkpoint(db: Session, user: str, task_id: str, p: CheckpointIn) -> dict:
    task = _task(db, user, task_id)
    if task.status != "doing":
        raise ServiceError(409, "Only a task that is in progress can be interrupted.")
    if not p.has_text():
        raise ServiceError(422, "Write at least one line in the checkpoint.")
    count = p.openItemsCount if p.openItemsCount is not None else len(p.openItems)
    pred = predict_difficulty(p.minutes, p.complexity, count, p.type)
    cp = m.Checkpoint(
        task_id=task.id, user_id=user, trigger=p.trigger, interruption_type=p.type, minutes=p.minutes,
        complexity=p.complexity, open_items_count=count, goal=p.goal, completed=p.completed, working_point=p.workingPoint,
        problem=p.problem, next_step=p.nextStep, resources=p.resources, open_items=p.openItems, files=p.files,
        level=pred["level"], score=pred["score"], depth=pred["depth"]["name"])
    db.add(cp)
    task.complexity = p.complexity
    task.status = "interrupted"
    filled = sum(1 for v in (p.goal, p.completed, p.workingPoint, p.problem, p.nextStep, p.resources) if v)
    log_event(db, user, "checkpoint_saved", task, {"level": pred["level"], "depth": pred["depth"]["name"],
                                                   "minutes": p.minutes, "type": p.type, "fields_filled": filled,
                                                   "files": len(p.files), "trigger": p.trigger})
    db.commit()
    return task_out(db, task)


def get_summary(db: Session, user: str, task_id: str, away_minutes: float | None, mode: str) -> dict:
    task = _task(db, user, task_id)
    cp = open_checkpoint(db, task)
    if cp is None:
        raise ServiceError(409, "This task has no open checkpoint.")
    away = _away(cp, away_minutes)
    data = _cp_dict(cp)
    template = build_summary(task.title, data, cp.level, away)
    result = generate_summary(mode, task.title, task.kind, data, cp.level, away)
    return {"intro": template["intro"], "lines": template["lines"], "text": result["text"], "level": cp.level,
            "depth": DEPTH[cp.level]["name"], "mode": result["mode"], "requestedMode": mode,
            "fallbackReason": result["fallback_reason"]}


def resume(db: Session, user: str, task_id: str, p: ResumeIn) -> dict:
    task = _task(db, user, task_id)
    cp = open_checkpoint(db, task)
    if cp is None:
        raise ServiceError(409, "This task has no open checkpoint.")
    away = _away(cp, p.awayMinutes)
    shown = p.shownText or template_text(task.title, _cp_dict(cp), cp.level, away)
    final = p.finalText if p.action == "edited" else None
    if p.action == "edited" and not (p.finalText or "").strip():
        raise ServiceError(422, "The edited summary is empty.")
    db.add(m.Resumption(checkpoint_id=cp.id, user_id=user, away_minutes=away, summary_mode=p.mode, summary_text=shown,
                        action=p.action, final_text=final, viewed_seconds=p.viewedSeconds))
    cp.resumed = True
    task.status = "doing"
    details = {"level": cp.level, "away_min": round(away), "viewed_s": round(p.viewedSeconds), "mode": p.mode}
    if p.action == "edited":
        details.update({"chars_before": len(shown), "chars_after": len(final or "")})
    log_event(db, user, f"summary_{p.action}", task, details)
    db.commit()
    return task_out(db, task)


# ------------------------------------------------------------------ log, export, demo
def add_event(db: Session, user: str, event: str, task_id: str | None, details: dict) -> None:
    task = _task(db, user, task_id) if task_id else None
    log_event(db, user, event, task, details)
    db.commit()


def list_events(db: Session, user: str) -> list[dict]:
    rows = db.scalars(select(m.EventLog).where(m.EventLog.user_id == user).order_by(m.EventLog.ts, m.EventLog.id)).all()
    return [{"ts": m.to_ms(e.ts), "event": e.event, "taskId": e.task_id or "", "task": e.task_title, "details": e.payload or {}}
            for e in rows]


def state(db: Session, user: str) -> dict:
    tasks = list_tasks(db, user)
    interruptions = db.scalar(select(func.count()).select_from(m.Checkpoint).where(m.Checkpoint.user_id == user)) or 0
    events = db.scalar(select(func.count()).select_from(m.EventLog).where(m.EventLog.user_id == user)) or 0
    return {"tasks": tasks, "interruptions": interruptions, "events": events}


def export_csv(db: Session, user: str) -> str:
    out = io.StringIO()
    w = csv.writer(out, quoting=csv.QUOTE_ALL)
    w.writerow(["time", "event", "task", "details"])
    for e in list_events(db, user):
        iso = m.datetime.fromtimestamp(e["ts"] / 1000, tz=m.timezone.utc).isoformat().replace("+00:00", "Z")
        w.writerow([iso, e["event"], e["task"], json.dumps(e["details"], ensure_ascii=False)])
    return out.getvalue()


def reset(db: Session, user: str) -> None:
    db.execute(delete(m.EventLog).where(m.EventLog.user_id == user))
    db.execute(delete(m.Resumption).where(m.Resumption.user_id == user))
    db.execute(delete(m.Checkpoint).where(m.Checkpoint.user_id == user))
    db.execute(delete(m.Task).where(m.Task.user_id == user))
    db.commit()
    seed_if_empty(db, user)


def load_demo(db: Session, user: str) -> None:
    reset(db, user)
    now = m.utcnow()
    tasks = {t.title: t for t in db.scalars(select(m.Task).where(m.Task.user_id == user)).all()}
    demo = [
        (tasks["Hotel booking website"], 300, "other_task", 3, {
            "goal": "Finish the hotel booking website for the web-technologies assignment",
            "completed": "login.html, register.html and home.html are finished",
            "workingPoint": "contact.html: the form has name and email fields but no submit handler",
            "problem": "Should the email be validated in JavaScript or on the server?",
            "nextStep": "Add the submit button and connect the form to the backend",
            "resources": "Figma UI link, contact.html",
            "openItems": ["validate email format", "add submit button and connect to backend", "show error message under the field"]}),
        (tasks["Database assignment report"], 20, "quick_message", 1, {
            "goal": "Complete the database assignment report",
            "completed": "ER diagram and normalisation to 3NF",
            "workingPoint": "Writing the SQL queries section",
            "problem": "", "nextStep": "Write the report queries and add references",
            "resources": "report_notes.md", "openItems": ["SQL queries for the reports section"]}),
    ]
    for task, minutes, type_, open_count, fields in demo:
        pred = predict_difficulty(minutes, task.complexity, open_count, type_)
        saved = now - timedelta(minutes=minutes)
        db.add(m.Checkpoint(
            task_id=task.id, user_id=user, created_at=saved, trigger="user", interruption_type=type_, minutes=minutes,
            complexity=task.complexity, open_items_count=open_count, goal=fields["goal"], completed=fields["completed"],
            working_point=fields["workingPoint"], problem=fields["problem"], next_step=fields["nextStep"],
            resources=fields["resources"], open_items=fields["openItems"], files=[], level=pred["level"],
            score=pred["score"], depth=pred["depth"]["name"]))
        task.status = "interrupted"
        log_event(db, user, "checkpoint_saved", task, {"level": pred["level"], "depth": pred["depth"]["name"],
                                                       "minutes": minutes, "demo": True}, ts=saved)
    db.commit()
