"""Request and response models. Field names are camelCase on purpose: they match the browser prototype."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Status = Literal["todo", "doing", "interrupted", "done"]
Complexity = Literal["simple", "moderate", "complex"]
InterruptionType = Literal["quick_message", "meeting", "other_task", "break"]
Mode = Literal["template", "lora"]

MAX_TEXT = 4000


class PredictIn(BaseModel):
    minutes: float | None = Field(default=None, ge=0, le=60 * 24 * 365)
    complexity: Complexity = "moderate"
    openItems: int = Field(default=0, ge=0, le=1000)
    type: InterruptionType = "meeting"


class Reason(BaseModel):
    text: str
    points: int


class PredictOut(BaseModel):
    score: int
    max: int
    level: Literal["Low", "Medium", "High"]
    depth: str
    suggested: list[str]
    reasons: list[Reason]


class CheckpointIn(BaseModel):
    goal: str = Field(default="", max_length=MAX_TEXT)
    completed: str = Field(default="", max_length=MAX_TEXT)
    workingPoint: str = Field(default="", max_length=MAX_TEXT)
    problem: str = Field(default="", max_length=MAX_TEXT)
    nextStep: str = Field(default="", max_length=MAX_TEXT)
    resources: str = Field(default="", max_length=MAX_TEXT)
    openItems: list[str] = Field(default_factory=list, max_length=200)
    files: list[str] = Field(default_factory=list, max_length=50)
    type: InterruptionType = "meeting"
    minutes: float = Field(default=30, ge=0, le=60 * 24 * 365)
    complexity: Complexity = "moderate"
    openItemsCount: int | None = Field(default=None, ge=0, le=1000)
    trigger: Literal["user", "notification"] = "user"

    @field_validator("goal", "completed", "workingPoint", "problem", "nextStep", "resources")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("openItems", "files")
    @classmethod
    def strip_items(cls, v: list[str]) -> list[str]:
        return [str(i).strip()[:500] for i in v if str(i).strip()]

    def has_text(self) -> bool:
        return any([self.goal, self.completed, self.workingPoint, self.problem, self.nextStep, self.resources])


class CheckpointOut(BaseModel):
    id: int
    goal: str
    completed: str
    workingPoint: str
    problem: str
    nextStep: str
    resources: str
    openItems: list[str]
    files: list[str]
    type: str
    minutes: float
    complexity: str
    level: str
    score: int
    depth: str
    trigger: str
    savedAt: int


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["code", "document"] = "code"
    complexity: Complexity = "moderate"

    @field_validator("title")
    @classmethod
    def strip_title(cls, v: str) -> str:
        return v.strip()


class TaskOut(BaseModel):
    id: str
    title: str
    kind: str
    complexity: str
    column: Status
    checkpoint: CheckpointOut | None = None


class MoveIn(BaseModel):
    column: Status


class SummaryLine(BaseModel):
    label: str
    text: str


class SummaryOut(BaseModel):
    intro: str
    lines: list[SummaryLine]
    text: str
    level: str
    depth: str
    mode: Mode
    requestedMode: Mode
    fallbackReason: str | None = None


class ResumeIn(BaseModel):
    action: Literal["accepted", "edited", "ignored"]
    finalText: str | None = Field(default=None, max_length=2 * MAX_TEXT)
    shownText: str | None = Field(default=None, max_length=4 * MAX_TEXT)
    viewedSeconds: float = Field(default=0, ge=0, le=60 * 60 * 24)
    awayMinutes: float | None = Field(default=None, ge=0, le=60 * 24 * 365)
    mode: Mode = "template"


class EventIn(BaseModel):
    event: str = Field(min_length=1, max_length=48, pattern=r"^[a-z_]+$")
    taskId: str | None = None
    details: dict = Field(default_factory=dict)


class EventOut(BaseModel):
    ts: int
    event: str
    taskId: str
    task: str
    details: dict


class StateOut(BaseModel):
    tasks: list[TaskOut]
    interruptions: int
    events: int
