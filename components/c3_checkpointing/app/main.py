"""Run C3 on its own:

    DATABASE_URL=sqlite:///./c3_demo.db uvicorn components.c3_checkpointing.app.main:app --reload

then open http://localhost:8000 (the browser prototype is served from app/static).
With the team's PostgreSQL (docker compose up -d db) leave DATABASE_URL unset.
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, text

from shared.db import Base, engine

from . import models  # noqa: F401  (registers the c3_ tables on the shared Base)
from .api import public, router

STATIC = Path(__file__).resolve().parent / "static"


def ensure_columns(bind) -> list[str]:
    """Add columns that a database created by an older version of C3 does not have yet.

    create_all only creates missing tables, never missing columns, so an old demo database would fail with
    "no such column". Only nullable JSON columns are added here; returns what was added.
    """
    added = []
    insp = inspect(bind)
    if not insp.has_table("c3_checkpoint"):
        return added
    have = {c["name"] for c in insp.get_columns("c3_checkpoint")}
    json_type = "JSONB" if bind.dialect.name == "postgresql" else "JSON"
    with bind.begin() as conn:
        if "file_snapshots" not in have:
            conn.execute(text(f"ALTER TABLE c3_checkpoint ADD COLUMN file_snapshots {json_type}"))
            added.append("c3_checkpoint.file_snapshots")
    return added


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Convenience for demos and tests. With PostgreSQL the team uses Alembic migrations instead.
    if os.environ.get("C3_AUTO_CREATE_TABLES", "1") == "1":
        Base.metadata.create_all(bind=engine)
        ensure_columns(engine)
    yield


class NoCacheStatic(StaticFiles):
    """The interface files change often: make the browser re-check them so it never mixes old and new scripts."""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
        return response


app = FastAPI(title="C3 Cognitive Checkpointing", version="0.1.0", lifespan=lifespan)
app.include_router(public)
app.include_router(router)
app.mount("/", NoCacheStatic(directory=STATIC, html=True), name="static")
