"""Read an MVD and record the user's decision: Accept / Edit / Reject
(CLAUDE.md §3.3 step 12). Each MVD can be decided once."""
from typing import Any

from fastapi import APIRouter, Body, Depends

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.models import EditBody, RejectBody
from components.c1_disruption.app.services import mvd_service
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.owned import load_owned

router = APIRouter(prefix="/mvds")


@router.get("/{mvd_id}")
def get_mvd(mvd_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return load_owned(deps.store, "mvds", mvd_id, user_id, "MVD")


@router.post("/{mvd_id}/accept")
def accept(
    mvd_id: str,
    body: Any = Body(default=None),  # ignored, as in the Node API
    user_id: str = Depends(require_user),
    deps: Deps = Depends(get_deps),
) -> dict:
    return mvd_service.decide(deps, user_id, mvd_id, "accept")


@router.post("/{mvd_id}/edit")
def edit(mvd_id: str, body: EditBody, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return mvd_service.decide(deps, user_id, mvd_id, "edit", changes=body.changes)


@router.post("/{mvd_id}/reject")
def reject(
    mvd_id: str,
    body: RejectBody | None = Body(default=None),
    user_id: str = Depends(require_user),
    deps: Deps = Depends(get_deps),
) -> dict:
    return mvd_service.decide(deps, user_id, mvd_id, "reject", reason=body.reason if body else None)
