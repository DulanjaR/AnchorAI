"""Pydantic request models, one per request body in docs/API.md.

Field checks and messages: validation.py. Rules that need more than one field or
stored data (e.g. "plannedEnd after plannedStart" on a PATCH) live in the routes
and services, as in the Node API.
"""
from typing import Any, ClassVar

from pydantic_core import PydanticCustomError

from components.c1_disruption.app.api.validation import (
    DISRUPTION_TYPES,
    PRIORITIES,
    TAGS,
    TASK_CATEGORIES,
    TASK_TYPES,
    Body,
    Date,
    DateTime,
    Flag,
    PositiveNumber,
    Text,
    Time,
    any_list,
    choice,
    non_empty_list,
    whole_number,
)

MINUTES_PER_DAY = 24 * 60


class SettingsBody(Body):
    REQUIRED = ("workStart", "workEnd")
    workStart: Time
    workEnd: Time


class ProtectedBlockBody(Body):
    """POST needs all three fields; PATCH may send any of them."""

    label: Text
    start: Time
    end: Time


class NewProtectedBlock(ProtectedBlockBody):
    REQUIRED = ("label", "start", "end")


class TaskBody(Body):
    """Fields the user may set. Status, timestamps and MVD tags are set by the API only."""

    title: Text
    type: choice(TASK_TYPES)
    priority: choice(PRIORITIES)
    estimatedHours: PositiveNumber
    deadline: DateTime
    delegable: Flag
    plannedDate: Date
    # The original plan slot is optional; it feeds the three-way comparison.
    plannedStart: Time
    plannedEnd: Time
    # Optional task category for ML Model 1 (16 Oct 2026); the engine ignores it.
    category: choice(TASK_CATEGORIES)


class NewTask(TaskBody):
    REQUIRED = ("title", "type", "priority", "estimatedHours", "deadline", "plannedDate")


class DisruptionReport(Body):
    REQUIRED = ("start", "timeLostMinutes", "date", "type", "severity")

    date: Date
    type: choice(DISRUPTION_TYPES)
    start: Time
    # Up to 23:59 of time lost; a full 24 h would make start and end equal.
    timeLostMinutes: whole_number(1, MINUTES_PER_DAY - 1)
    # Stored for the bandit (Task 5); it does not change the MVD.
    severity: whole_number(1, 3)
    suggestedType: choice(DISRUPTION_TYPES)
    confirmed: Any = None

    @classmethod
    def pre_check(cls, data: dict[str, Any]) -> None:
        # No MVD without the user's confirmation (CLAUDE.md rule 5), explicit in every request.
        if data.get("confirmed") is not True:
            raise PydanticCustomError(
                "c1_invalid",
                "'confirmed' must be true: the user has to confirm the disruption first",
                {"code": "NOT_CONFIRMED"},
            )


class ManualReplanItem(Body):
    NOT_OBJECT: ClassVar[str] = "Each 'manualReplan' item must be an object"
    REQUIRED = ("taskId",)
    taskId: Text
    tag: choice(TAGS)
    start: Time
    end: Time


class GenerateBody(Body):
    planFrom: Time
    manualReplan: any_list(ManualReplanItem)


class EditChange(Body):
    NOT_OBJECT: ClassVar[str] = "Each item in 'changes' must be an object"
    REQUIRED = ("taskId",)
    taskId: Text
    tag: choice(TAGS)
    start: Time
    end: Time


class EditBody(Body):
    REQUIRED = ("changes",)
    changes: non_empty_list(EditChange)


class RejectBody(Body):
    reason: Text


class ReviewItem(Body):
    NOT_OBJECT: ClassVar[str] = "Each item must be an object"
    REQUIRED = ("taskId", "outcome")
    taskId: Text
    outcome: choice(("done", "partial", "not_done"))
    partialPct: choice((25, 50, 75))


class ReviewBody(Body):
    REQUIRED = ("items",)
    items: non_empty_list(ReviewItem)
