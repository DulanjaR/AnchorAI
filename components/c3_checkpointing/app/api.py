"""C3 REST routes. The router can be mounted by the orchestration layer or run on its own (app/main.py)."""
from __future__ import annotations

import os
import re

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from shared.auth import require_api_key
from shared.db import get_db

from ..parser.text_files import MAX_BYTES, analyze_file, suggest_from_file
from . import schemas as s
from . import service
from .generators import get_lora

USER_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
public = APIRouter(prefix="/api")


def current_user(x_user_id: str = Header(default="demo-user")) -> str:
    """Pseudonymous participant id (never a name or e-mail)."""
    if not USER_ID.match(x_user_id):
        raise HTTPException(400, "X-User-Id must be 1-64 letters, digits, '-' or '_'.")
    return x_user_id


def run(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except service.ServiceError as exc:
        raise HTTPException(exc.status, exc.message) from exc


@public.get("/health")
def health():
    return {"status": "ok", "component": "c3_checkpointing", "modes": ["template"] + (["lora"] if get_lora() else [])}


@router.post("/predict", response_model=s.PredictOut)
def predict(body: s.PredictIn):
    return service.predict(body.minutes, body.complexity, body.openItems, body.type)


@router.get("/state", response_model=s.StateOut)
def get_state(db: Session = Depends(get_db), user: str = Depends(current_user)):
    return service.state(db, user)


@router.get("/tasks", response_model=list[s.TaskOut])
def list_tasks(db: Session = Depends(get_db), user: str = Depends(current_user)):
    return service.list_tasks(db, user)


@router.post("/tasks", response_model=s.TaskOut, status_code=201)
def create_task(body: s.TaskIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return service.create_task(db, user, body.title, body.kind, body.complexity)


@router.patch("/tasks/{task_id}", response_model=s.TaskOut)
def move_task(task_id: str, body: s.MoveIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return run(service.move_task, db, user, task_id, body.column)


@router.post("/tasks/{task_id}/checkpoint", response_model=s.TaskOut, status_code=201)
def save_checkpoint(task_id: str, body: s.CheckpointIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return run(service.save_checkpoint, db, user, task_id, body)


@router.get("/tasks/{task_id}/summary", response_model=s.SummaryOut)
def summary(task_id: str, awayMinutes: float | None = Query(default=None, ge=0, le=60 * 24 * 365),
            mode: s.Mode = "template", db: Session = Depends(get_db), user: str = Depends(current_user)):
    return run(service.get_summary, db, user, task_id, awayMinutes, mode)


@router.post("/tasks/{task_id}/resume", response_model=s.TaskOut)
def resume(task_id: str, body: s.ResumeIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    return run(service.resume, db, user, task_id, body)


@router.post("/files/analyze")
async def analyze_files(files: list[UploadFile] = File(...)):
    """Read-only analysis. Only small facts are returned; the file text is neither stored nor logged."""
    if len(files) > 10:
        raise HTTPException(413, "At most 10 files at a time.")
    out = []
    for f in files:
        data = await f.read(MAX_BYTES + 1)
        insight = analyze_file(f.filename or "file", data)
        insight["suggest"] = suggest_from_file(insight)
        out.append(insight)
    return {"files": out}


@router.post("/events", status_code=201)
def add_event(body: s.EventIn, db: Session = Depends(get_db), user: str = Depends(current_user)):
    run(service.add_event, db, user, body.event, body.taskId, body.details)
    return {"ok": True}


@router.get("/events", response_model=list[s.EventOut])
def events(db: Session = Depends(get_db), user: str = Depends(current_user)):
    return service.list_events(db, user)


@router.get("/export.csv", response_class=PlainTextResponse)
def export_csv(db: Session = Depends(get_db), user: str = Depends(current_user)):
    return PlainTextResponse(service.export_csv(db, user), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="c3_study_log.csv"'})


def _demo_allowed() -> None:
    if os.environ.get("C3_ALLOW_RESET", "1") != "1":
        raise HTTPException(403, "Reset and demo data are disabled on this server.")


@router.post("/reset", status_code=204)
def reset(db: Session = Depends(get_db), user: str = Depends(current_user)):
    _demo_allowed()
    service.reset(db, user)


@router.post("/demo", status_code=204)
def demo(db: Session = Depends(get_db), user: str = Depends(current_user)):
    _demo_allowed()
    service.load_demo(db, user)
