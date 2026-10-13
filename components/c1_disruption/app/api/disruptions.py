"""Disruption reports. The app sends one only after the user has confirmed type,
time lost and severity (CLAUDE.md §3.4); passive signals alone never create one.
`confirmed: true` must be sent explicitly, so this rule is visible in every request."""
from fastapi import APIRouter, Body, Depends

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.models import MINUTES_PER_DAY, DisruptionReport, GenerateBody
from components.c1_disruption.app.services import mvd_service
from components.c1_disruption.app.services.clock import iso_utc
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.owned import load_owned
from components.c1_disruption.engine.time import to_hhmm, to_minutes

router = APIRouter(prefix="/disruptions")


@router.post("", status_code=201)
def report(body: DisruptionReport, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    disruption = {
        "userId": user_id,
        "date": body.date,
        "type": body.type,
        "start": body.start,
        "timeLostMinutes": body.timeLostMinutes,
        # Window end = start + time lost. If it passes midnight (e.g. 20:00 + 6 h =
        # 02:00), the engine clips the window at the end of the plan day.
        "end": to_hhmm((to_minutes(body.start) + body.timeLostMinutes) % MINUTES_PER_DAY),
        "severity": body.severity,
        "suggestedType": body.suggestedType,
        "confirmed": True,
        "reportedAt": iso_utc(deps.clock.now()),
    }
    return deps.store.create("disruptions", disruption)


@router.get("/{disruption_id}")
def get_disruption(disruption_id: str, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    return load_owned(deps.store, "disruptions", disruption_id, user_id, "Disruption")


@router.post("/{disruption_id}/mvd", status_code=201)
def generate_mvd(
    disruption_id: str,
    body: GenerateBody | None = Body(default=None),
    user_id: str = Depends(require_user),
    deps: Deps = Depends(get_deps),
) -> dict:
    """Generate a PROPOSED MVD. The user still has to accept, edit or reject it."""
    disruption = load_owned(deps.store, "disruptions", disruption_id, user_id, "Disruption")
    body = body or GenerateBody()
    return mvd_service.generate(deps, user_id, disruption, plan_from=body.planFrom, manual_replan=body.manualReplan)
