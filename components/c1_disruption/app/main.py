"""Component 1 (Disruption Recovery Planner) FastAPI app.

One service for the MVD API and the ML endpoints. Phase 2 (structure) only has
/health; the /api routes come with Phase 4 and the ML routes with Phase 5.

Run from the repo root:
    uvicorn components.c1_disruption.app.main:app --reload
"""
from fastapi import FastAPI

app = FastAPI(title="Anchor AI - C1 Disruption Recovery Planner", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "component": "c1_disruption"}
