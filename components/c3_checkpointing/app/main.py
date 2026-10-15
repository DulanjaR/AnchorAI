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

from shared.db import Base, engine

from . import models  # noqa: F401  (registers the c3_ tables on the shared Base)
from .api import public, router

STATIC = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Convenience for demos and tests. With PostgreSQL the team uses Alembic migrations instead.
    if os.environ.get("C3_AUTO_CREATE_TABLES", "1") == "1":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="C3 Cognitive Checkpointing", version="0.1.0", lifespan=lifespan)
app.include_router(public)
app.include_router(router)
app.mount("/", StaticFiles(directory=STATIC, html=True), name="static")
