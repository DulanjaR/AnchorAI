"""Component 1 (Disruption Recovery Planner) FastAPI app.

One service for the MVD API (docs/API.md) and, from Phase 5, the ML endpoints.

    create_app(store, clock)  builds an app; tests pass a fresh store and a fixed clock
    app                       the app uvicorn serves (in-memory store, system clock)

Run from the repo root:
    uvicorn components.c1_disruption.app.main:app --reload

Every route needs the team API key (X-API-Key, shared.auth.require_api_key);
every /api route also needs X-User-Id (stand-in for user auth).
"""
from fastapi import Depends, FastAPI

from components.c1_disruption.app.api import disruptions, mvds, protected_blocks, rearrange, reviews, settings, tasks
from components.c1_disruption.app.api.deps import require_user
from components.c1_disruption.app.api.errors import install_error_handlers
from components.c1_disruption.app.data.memory_store import MemoryStore
from components.c1_disruption.app.data.repository import Repository
from components.c1_disruption.app.services.clock import Clock, SystemClock
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.planning import DriftCorrector, FixedOrder, NoDrift, StrategyChooser
from components.c1_disruption.app.settings import c1_settings
from shared.auth import require_api_key


def default_corrector(path: str) -> DriftCorrector:
    """ML Model 1 from C1_DRIFT_MODEL_PATH; empty → NoDrift (drift 1.0). The ML
    packages are only imported when a model file is configured."""
    if not path:
        return NoDrift()
    from components.c1_disruption.ml.drift.corrector import load_corrector

    return load_corrector(path)


def create_app(
    store: Repository | None = None,
    clock: Clock | None = None,
    api_prefix: str | None = None,
    corrector: DriftCorrector | None = None,
    chooser: StrategyChooser | None = None,
) -> FastAPI:
    """corrector / chooser = ML Model 1 / 2 hooks (services/planning.py); the
    defaults (drift 1.0, fixed order) keep the approved behaviour."""
    app = FastAPI(title="Anchor AI - C1 Disruption Recovery Planner", version="0.2.0")
    app.state.deps = Deps(
        store=MemoryStore() if store is None else store,
        clock=SystemClock() if clock is None else clock,
        corrector=default_corrector(c1_settings.drift_model_path) if corrector is None else corrector,
        chooser=FixedOrder() if chooser is None else chooser,
    )
    install_error_handlers(app)

    @app.get("/health", dependencies=[Depends(require_api_key)])
    def health() -> dict[str, str]:
        return {"status": "ok", "component": "c1_disruption"}

    prefix = c1_settings.api_prefix if api_prefix is None else api_prefix
    # API key first (team-wide), then the caller's user id.
    guarded = [Depends(require_api_key), Depends(require_user)]
    for module in (settings, protected_blocks, tasks, disruptions, mvds, reviews, rearrange):
        app.include_router(module.router, prefix=prefix, dependencies=guarded)
    return app


app = create_app()
