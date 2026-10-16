"""HCDE HTTP API (see docs/api-contract.md)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import service
from ..db.models import Interaction, Probe
from ...generation import ollama_client

router = APIRouter(prefix="/hcde", tags=["hcde"])
SessionFactory = None  # set by main.py


def get_db():
    db = SessionFactory()
    try:
        yield db
    finally:
        db.close()


class RecommendIn(BaseModel):
    user_id: str = Field(..., max_length=64, description="pseudonymous id")
    task: str = Field(..., min_length=3, max_length=8000)
    minutes_left: Optional[float] = Field(None, ge=0, description="time until the deadline, if any")
    difficulty_hint: Optional[int] = Field(None, ge=1, le=5)


class RespondIn(BaseModel):
    tier: Optional[str] = Field(None, description="omit to accept the recommendation; any tier to override")
    student_attempt: Optional[str] = None


class OutcomeIn(BaseModel):
    solved: bool


class CheckIn(BaseModel):
    answer: str = Field(..., min_length=1, max_length=12000)


class ProbeIn(BaseModel):
    user_id: str
    skill: Optional[str] = None
    context: Optional[str] = None
    interaction_id: Optional[int] = None


class AnswerIn(BaseModel):
    answer: str = Field(..., min_length=1, max_length=8000)


def _interaction(it: Interaction) -> dict:
    return {"interaction_id": it.id, "user_id": it.user_id, "task": it.task, "skill": it.skill, "context": it.context, "module": it.module,
            "difficulty": it.difficulty, "urgency": it.urgency, "recommended_tier": it.recommended_tier,
            "explanation": it.decision["explanation"], "decision": it.decision, "chosen_tier": it.chosen_tier,
            "overridden": it.overridden, "reply": it.reply, "generation": it.generation, "outcome": it.outcome,
            "verified": it.verified, "checks": it.checks}


@router.get("/status")
def status() -> dict:
    return {"model": ollama_client.HCDE_MODEL, "model_available": ollama_client.available()}


@router.post("/recommend")
def recommend(body: RecommendIn, db: Session = Depends(get_db)) -> dict:
    return _interaction(service.recommend_for(db, body.user_id, body.task, body.minutes_left, body.difficulty_hint))


@router.post("/interactions/{interaction_id}/respond")
def respond(interaction_id: int, body: RespondIn, db: Session = Depends(get_db)) -> dict:
    try:
        return _interaction(service.respond(db, interaction_id, body.tier, body.student_attempt))
    except service.NotFound:
        raise HTTPException(404, "interaction not found")
    except ValueError as e:
        raise HTTPException(422, str(e))
    except OSError as e:  # Ollama not running
        raise HTTPException(503, f"model not reachable: {e}")


@router.post("/interactions/{interaction_id}/outcome")
def outcome(interaction_id: int, body: OutcomeIn, db: Session = Depends(get_db)) -> dict:
    try:
        return service.record_outcome(db, interaction_id, body.solved)
    except service.NotFound:
        raise HTTPException(404, "interaction not found")


@router.post("/interactions/{interaction_id}/check")
def check(interaction_id: int, body: CheckIn, db: Session = Depends(get_db)) -> dict:
    """Check my answer: graded against a hidden reference; feedback respects the chosen tier."""
    try:
        return service.check_answer(db, interaction_id, body.answer)
    except service.NotFound:
        raise HTTPException(404, "interaction not found")
    except OSError as e:
        raise HTTPException(503, f"model not reachable: {e}")


@router.post("/probes")
def create_probe(body: ProbeIn, db: Session = Depends(get_db)) -> dict:
    try:
        p = service.create_probe(db, body.user_id, body.skill, body.interaction_id, context=body.context)
    except service.NotFound as e:
        raise HTTPException(404, str(e))
    except OSError as e:
        raise HTTPException(503, f"model not reachable: {e}")
    return {"probe_id": p.id, "skill": p.skill, "context": p.context, "problem": p.problem}  # the answer key stays on the server


@router.post("/probes/{probe_id}/answer")
def answer_probe(probe_id: int, body: AnswerIn, db: Session = Depends(get_db)) -> dict:
    try:
        return service.answer_probe(db, probe_id, body.answer)
    except service.NotFound:
        raise HTTPException(404, "probe not found")


@router.get("/users/{user_id}/ledger")
def ledger(user_id: str, db: Session = Depends(get_db)) -> dict:
    return {"user_id": user_id, "skills": service.ledger_for(db, user_id)}


@router.get("/users/{user_id}/history")
def history(user_id: str, limit: int = 20, db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(Interaction).where(Interaction.user_id == user_id)
                      .order_by(Interaction.id.desc()).limit(limit)).all()
    probes = db.scalars(select(Probe).where(Probe.user_id == user_id).order_by(Probe.id.desc()).limit(limit)).all()
    return {"interactions": [_interaction(r) for r in rows],
            "probes": [{"probe_id": p.id, "skill": p.skill, "status": p.status, "problem": p.problem} for p in probes]}
