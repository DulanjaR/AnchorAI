"""C3 tables. They share the team's SQLAlchemy Base (shared/db.py) and are prefixed with c3_.

JSON columns are JSONB on PostgreSQL and plain JSON on SQLite, so the same code runs in both.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from shared.db import Base

JsonType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def to_ms(value: datetime | None) -> int | None:
    if value is None:
        return None
    return int(value.replace(tzinfo=timezone.utc).timestamp() * 1000)


class Task(Base):
    __tablename__ = "c3_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)  # pseudonymous id, never a name or email
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(16), default="code")  # code | document
    complexity: Mapped[str] = mapped_column(String(16), default="moderate")
    status: Mapped[str] = mapped_column(String(16), default="todo")  # todo | doing | interrupted | done
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    checkpoints: Mapped[list[Checkpoint]] = relationship(back_populates="task", cascade="all, delete-orphan")


class Checkpoint(Base):
    __tablename__ = "c3_checkpoint"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("c3_task.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    trigger: Mapped[str] = mapped_column(String(16), default="user")  # user | notification
    interruption_type: Mapped[str] = mapped_column(String(24))
    minutes: Mapped[float] = mapped_column(Float)
    complexity: Mapped[str] = mapped_column(String(16))
    open_items_count: Mapped[int] = mapped_column(Integer, default=0)

    goal: Mapped[str] = mapped_column(Text, default="")
    completed: Mapped[str] = mapped_column(Text, default="")
    working_point: Mapped[str] = mapped_column(Text, default="")
    problem: Mapped[str] = mapped_column(Text, default="")
    next_step: Mapped[str] = mapped_column(Text, default="")
    resources: Mapped[str] = mapped_column(Text, default="")
    open_items: Mapped[list] = mapped_column(JsonType, default=list)  # texts found in the student's own files
    files: Mapped[list] = mapped_column(JsonType, default=list)  # file names only; file text is never stored

    level: Mapped[str] = mapped_column(String(8))
    score: Mapped[int] = mapped_column(Integer)
    depth: Mapped[str] = mapped_column(String(16))
    resumed: Mapped[bool] = mapped_column(Boolean, default=False)

    task: Mapped[Task] = relationship(back_populates="checkpoints")
    resumptions: Mapped[list[Resumption]] = relationship(back_populates="checkpoint", cascade="all, delete-orphan")


class Resumption(Base):
    __tablename__ = "c3_resumption"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    checkpoint_id: Mapped[int] = mapped_column(ForeignKey("c3_checkpoint.id"), index=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    resumed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    away_minutes: Mapped[float] = mapped_column(Float)
    summary_mode: Mapped[str] = mapped_column(String(16))  # template | lora
    summary_text: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(16))  # accepted | edited | ignored
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    viewed_seconds: Mapped[float] = mapped_column(Float, default=0.0)

    checkpoint: Mapped[Checkpoint] = relationship(back_populates="resumptions")


class EventLog(Base):
    __tablename__ = "c3_event_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    task_title: Mapped[str] = mapped_column(String(200), default="")
    event: Mapped[str] = mapped_column(String(48), index=True)
    payload: Mapped[dict] = mapped_column(JsonType, default=dict)
    ts: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
