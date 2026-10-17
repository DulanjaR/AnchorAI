"""Rearranger endpoints (17 Oct 2026): propose where moved tasks and effort sessions go over
the next 7 days; the student chooses options A–E where needed, then accepts / edits / rejects."""
from typing import Any

from fastapi import APIRouter, Body, Depends

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.models import ChooseOption, RearrangeEditBody, RearrangeRequest, RejectBody
from components.c1_disruption.app.services import rearrange_service
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.owned import load_owned

router = APIRouter()


@router.post("/rearrange", status_code=201)
def propose(body: RearrangeRequest, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return rearrange_service.create(deps, user_id, body.date)


@router.get("/rearrangements/{rid}")
def get_one(rid: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return load_owned(deps.store, "rearrangements", rid, user_id, "Rearrangement")


@router.post("/rearrangements/{rid}/choose")
def choose(rid: str, body: ChooseOption, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return rearrange_service.choose(deps, user_id, rid, body.taskId, body.option)


@router.post("/rearrangements/{rid}/accept")
def accept(rid: str, body: Any = Body(default=None), user_id: str = Depends(require_user),
           deps: Deps = Depends(get_deps)) -> dict:
    return rearrange_service.decide(deps, user_id, rid, "accept")


@router.post("/rearrangements/{rid}/edit")
def edit(rid: str, body: RearrangeEditBody, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return rearrange_service.decide(deps, user_id, rid, "edit", changes=body.changes)


@router.post("/rearrangements/{rid}/reject")
def reject(rid: str, body: RejectBody | None = Body(default=None), user_id: str = Depends(require_user),
           deps: Deps = Depends(get_deps)) -> dict:
    return rearrange_service.decide(deps, user_id, rid, "reject", reason=body.reason if body else None)
