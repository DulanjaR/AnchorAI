"""Work hours per user. The MVD plans only inside these hours."""
from fastapi import APIRouter, Depends

from components.c1_disruption.app.api.deps import get_deps, require_user
from components.c1_disruption.app.api.errors import bad_request, not_found
from components.c1_disruption.app.api.models import SettingsBody
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.engine.time import to_minutes

router = APIRouter(prefix="/me/settings")


@router.get("")
def get_settings(user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    user = deps.store.get("users", user_id)
    if user is None:
        raise not_found("Settings (set work hours first)")
    return user


@router.put("")
def put_settings(body: SettingsBody, user_id: str = Depends(require_user), deps: Deps = Depends(get_deps)) -> dict:
    if to_minutes(body.workEnd) <= to_minutes(body.workStart):
        raise bad_request("'workEnd' must be after 'workStart'")
    return deps.store.set("users", user_id, {"workStart": body.workStart, "workEnd": body.workEnd})
