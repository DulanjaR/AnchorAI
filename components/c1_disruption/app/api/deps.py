"""FastAPI dependencies shared by the C1 routers."""
from fastapi import Header, Request

from components.c1_disruption.app.api.errors import ApiError
from components.c1_disruption.app.services.mvd_service import Deps


def require_user(x_user_id: str | None = Header(default=None)) -> str:
    """Who is calling. STAND-IN until real user auth exists (approved 8 Oct 2026):
    the client sends X-User-Id. The team-wide X-API-Key check (shared.auth) runs
    before this on every route."""
    if x_user_id is None or not x_user_id.strip():
        raise ApiError(401, "NO_USER", "Missing X-User-Id header")
    return x_user_id.strip()


def get_deps(request: Request) -> Deps:
    """The store and clock given to create_app (app.state), so tests can inject them."""
    return request.app.state.deps
