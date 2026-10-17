"""Pydantic request models, one per request body in docs/API.md.

Field checks and messages: validation.py. Rules that need more than one field or
stored data (e.g. "plannedEnd after plannedStart" on a PATCH) live in the routes
and services, as in the Node API.
"""
from typing import Any, ClassVar

from pydantic_core import PydanticCustomError

from components.c1_disruption.app.api.validation import (
    DISRUPTION_TYPES,
    LOCATIONS,
    OPTION_CODES,
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


class RoutineBlock(Body):
    """Where the student usually is at a time of day (17 Oct 2026): it gives each study
    window its location and pre-fills a task's location. Free time, not busy time."""

    NOT_OBJECT: ClassVar[str] = "Each 'routine' item must be an object"
    REQUIRED = ("label", "start", "end", "location")
    label: Text
    start: Time
    end: Time
    location: choice(LOCATIONS)


class SettingsBody(Body):
    REQUIRED = ("workStart", "workEnd")
    workStart: Time
    workEnd: Time
    # Optional (17 Oct 2026); stored only when sent, so the earlier settings object is unchanged.
    routine: any_list(RoutineBlock)


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
    # Optional (17 Oct 2026, rearranger): where it is done (a label, no GPS) and effort-task fields.
    location: choice(LOCATIONS)
    totalEffortMinutes: whole_number(1, 100_000)
    minSession: whole_number(5, MINUTES_PER_DAY)
    maxSession: whole_number(5, MINUTES_PER_DAY)
    splittable: Flag


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


class RearrangeRequest(Body):
    REQUIRED = ("date",)
    date: Date


class ChooseOption(Body):
    REQUIRED = ("taskId", "option")
    taskId: Text
    option: choice(OPTION_CODES)


class SessionDone(Body):
    REQUIRED = ("date",)
    date: Date


class RearrangeChange(Body):
    NOT_OBJECT: ClassVar[str] = "Each item in 'changes' must be an object"
    REQUIRED = ("taskId", "date", "start", "end")
    taskId: Text
    date: Date
    start: Time
    end: Time


class RearrangeEditBody(Body):
    REQUIRED = ("changes",)
    changes: non_empty_list(RearrangeChange)


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
