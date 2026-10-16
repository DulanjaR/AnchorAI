"""HCDE database.

Shared deployment: Supabase (PostgreSQL), set in .env as
    HCDE_DATABASE_URL=postgresql+psycopg://postgres.<project>:<password>@<host>:5432/postgres
Local fallback / tests: SQLite file runs/hcde.db (used when HCDE_DATABASE_URL is not set).
All tables are prefixed "hcde_" so the four Anchor AI components can share one database.
Stores pseudonymous user ids only: no names or emails.
"""
from __future__ import annotations

from typing import Optional

import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

ROOT = Path(__file__).resolve().parents[4]


def _from_dotenv(name: str) -> Optional[str]:
    """Read one setting from the repo's .env (so `uvicorn` works without `source .env`)."""
    env = ROOT / ".env"
    if not env.exists():
        return None
    for line in env.read_text().splitlines():
        if line.strip().startswith(f"{name}="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return None


DATABASE_URL = (os.environ.get("HCDE_DATABASE_URL") or _from_dotenv("HCDE_DATABASE_URL")
                or f"sqlite:///{ROOT / 'runs' / 'hcde.db'}")


def now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Interaction(Base):
    """One task the student brought: the recommendation, what they chose, the reply and the outcome."""
    __tablename__ = "hcde_interactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    task: Mapped[str] = mapped_column(Text)
    skill: Mapped[str] = mapped_column(String(80), index=True)
    context: Mapped[str] = mapped_column(String(30), default="general")
    module: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[int] = mapped_column(Integer)
    urgency: Mapped[float] = mapped_column(Float)
    profile: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[dict] = mapped_column(JSON)
    recommended_tier: Mapped[str] = mapped_column(String(20))
    chosen_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    generation: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # "solved" / "not_solved"
    verified: Mapped[bool] = mapped_column(Boolean, default=False)   # outcome from a checked answer, not self-report
    checks: Mapped[int] = mapped_column(Integer, default=0)          # how many times the student checked an answer
    reference: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # hidden reference solution for checking
    test_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # SQL test database for executing answers


class SkillStateRow(Base):
    __tablename__ = "hcde_skill_states"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    skill: Mapped[str] = mapped_column(String(80), primary_key=True)
    context: Mapped[str] = mapped_column(String(30), primary_key=True, default="general")
    module: Mapped[str] = mapped_column(String(80), default="General")
    mastery: Mapped[float] = mapped_column(Float, default=0.3)
    prior: Mapped[float] = mapped_column(Float, default=0.3)          # starting estimate (transfer prior)
    prior_note: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    observations: Mapped[int] = mapped_column(Integer, default=0)
    success_streak: Mapped[int] = mapped_column(Integer, default=0)
    fail_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_tier: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    borrowed: Mapped[float] = mapped_column(Float, default=0.0)
    built: Mapped[float] = mapped_column(Float, default=0.0)
    repaid: Mapped[float] = mapped_column(Float, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class LedgerEntry(Base):
    """Capability Ledger: every unit of help borrowed and every unaided success / probe that repays it."""
    __tablename__ = "hcde_ledger"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    skill: Mapped[str] = mapped_column(String(80))
    context: Mapped[str] = mapped_column(String(30), default="general")
    kind: Mapped[str] = mapped_column(String(20))   # "borrowed" | "built" | "repaid"
    amount: Mapped[float] = mapped_column(Float)
    interaction_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hcde_interactions.id"), nullable=True)
    probe_id: Mapped[Optional[int]] = mapped_column(ForeignKey("hcde_probes.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Check(Base):
    """Every 'check my answer': the answer, the grade, and the tier-calibrated feedback shown."""
    __tablename__ = "hcde_checks"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    interaction_id: Mapped[int] = mapped_column(ForeignKey("hcde_interactions.id"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    answer: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(10))
    feedback: Mapped[str] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Calibration(Base):
    """First-task calibration answers per subject (proposal 3.2): seeds the Capability Profile before
    there is any history. Self-report only sets the starting point; observed outcomes take over."""
    __tablename__ = "hcde_calibration"
    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    module: Mapped[str] = mapped_column(String(80), primary_key=True)
    confidence: Mapped[int] = mapped_column(Integer)            # 1-5
    experience: Mapped[str] = mapped_column(String(20))         # never / a_few / often
    preference: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # try_first / guidance_early
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Probe(Base):
    __tablename__ = "hcde_probes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    skill: Mapped[str] = mapped_column(String(80))
    context: Mapped[str] = mapped_column(String(30), default="general")
    source_task: Mapped[str] = mapped_column(Text)
    problem: Mapped[str] = mapped_column(Text)
    answer_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open / passed / failed
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


def _reset_outdated_local_schema(engine, url: str) -> None:
    """Local SQLite only: if the tables predate the language/tool 'context' column, drop the HCDE tables
    (test data) so they are recreated with the new layout. Never touches Postgres/Supabase."""
    if not url.startswith("sqlite"):
        return
    from sqlalchemy import inspect
    insp = inspect(engine)
    if "hcde_skill_states" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("hcde_skill_states")}
        icols = {c["name"] for c in insp.get_columns("hcde_interactions")} if "hcde_interactions" in insp.get_table_names() else set()
        if "context" not in cols or "test_data" not in icols:
            print("HCDE: local database is from an older version; resetting HCDE tables (test data only).")
            Base.metadata.drop_all(engine)


def make_session_factory(url: Optional[str] = None):
    url = url or DATABASE_URL
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    if url.startswith("sqlite"):
        engine = create_engine(url, connect_args={"check_same_thread": False})
    else:  # Supabase / Postgres: keep connections healthy through the pooler
        engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5)
    _reset_outdated_local_schema(engine, url)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
