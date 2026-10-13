"""Shapes of the engine's input and output (type hints only, no logic).

Keys are camelCase on purpose: they are the same as the golden JSON
(tests/golden/) and the API contract (docs/API.md), so data passes through the
API unchanged.
"""
from typing import NotRequired, TypedDict


class WorkHours(TypedDict):
    start: str  # 'HH:MM'
    end: str


class Disruption(TypedDict):
    type: str
    start: str  # 'HH:MM'
    end: str  # 'HH:MM'; earlier than start = crosses midnight (clipped at 24:00)


class ProtectedBlock(TypedDict):
    id: str
    label: NotRequired[str]
    start: str
    end: str  # may cross midnight (sleep 22:00-06:00)


class TaskInput(TypedDict):
    id: str
    title: str
    type: str  # one of config.TASK_TYPES
    priority: str  # High / Medium / Low
    estimatedHours: float  # AFTER drift correction (drift = 1.0 until ML Model 1)
    deadline: str  # 'YYYY-MM-DDTHH:MM' (a bare date = end of that day)
    delegable: NotRequired[bool]


class MvdInput(TypedDict):
    date: str  # 'YYYY-MM-DD'
    workHours: WorkHours
    planFrom: NotRequired[str | None]  # defaults to workHours.start
    disruption: Disruption
    protectedBlocks: NotRequired[list[ProtectedBlock]]
    tasks: NotRequired[list[TaskInput]]


class MvdTask(TypedDict):
    id: str
    title: str
    type: str
    priority: str
    deadline: str
    daysUntilDeadline: int
    estimatedHours: float
    delegable: bool
    efUsed: float
    fi: float
    group: str  # A / B / C / D
    tag: str  # Keep / Reduce / Move / Delegate
    start: str | None
    end: str | None
    compressionPct: float | None
    reason: str
    deadlineRisk: bool
    explanation: str


class ProtectOutput(TypedDict):
    id: str
    label: str | None
    tag: str  # always 'Protect'
    start: str
    end: str
    reason: str  # always 'PROTECTED_BLOCK'
    explanation: str


class Warning(TypedDict):
    taskId: str
    code: str  # 'DEADLINE_RISK'
    message: str


class Mvd(TypedDict):
    date: str
    disruption: dict[str, str]  # the input disruption + 'kind'
    horizon: WorkHours
    tasks: list[MvdTask]  # in placement order
    protect: list[ProtectOutput]
    freeMinutesLeft: int
    warnings: list[Warning]
