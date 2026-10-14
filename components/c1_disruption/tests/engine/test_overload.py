import copy

import pytest

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.engine.overload import check_overload
from components.c1_disruption.tests.golden.loader import scenario


def day(tasks, **over):
    return {
        "date": "2026-10-07",
        "workHours": {"start": "09:00", "end": "17:00"},
        "planFrom": "09:00",
        "protectedBlocks": [{"id": "lunch", "label": "Lunch", "start": "12:00", "end": "13:00"}],
        "tasks": tasks,
        **over,
    }


def task(id, hours, deadline="2026-10-08T23:59", **over):
    return {"id": id, "title": id, "type": "Digital", "priority": "High", "estimatedHours": hours,
            "deadline": deadline, **over}


def test_a_day_that_fits():
    report = check_overload(day([task("A", 2), task("B", 3)]))
    # 09:00–17:00 minus lunch = 420 min; planned 300.
    assert report["availableMinutes"] == 420
    assert report["plannedMinutes"] == 300
    assert report["slackRatio"] == pytest.approx(120 / 420)
    assert report["overloaded"] is False
    assert report["deadlineWarnings"] == []


def test_overloaded_with_point_and_only_with_high():
    report = check_overload(day([task("A", 3), task("B", 3, estimatedHoursHigh=4.5)]))
    assert (report["plannedMinutes"], report["plannedMinutesHigh"]) == (360, 450)
    assert (report["overloaded"], report["overloadedHigh"]) == (False, True)
    assert report["slackRatioHigh"] == pytest.approx(-30 / 420)


def test_plan_from_and_protected_blocks_reduce_available_time():
    report = check_overload(day([], planFrom="14:00"))
    assert report["availableMinutes"] == 180
    assert report["slackRatio"] == 1.0


def test_early_deadline_warning_in_deadline_order():
    # Free before 11:00: 09:00–11:00 = 120 → A (120) fits exactly, not flagged.
    # Free before 12:30: 09:00–12:00 = 180 (lunch from 12:00) → A + B = 210 > 180, flagged.
    # C is due in 2 days: not checked.
    tasks = [task("A", 2, "2026-10-07T11:00"), task("B", 1.5, "2026-10-07T12:30"), task("C", 1, "2026-10-09T12:00")]
    report = check_overload(day(tasks))
    assert report["deadlineWarnings"] == [
        {"taskId": "B", "deadline": "2026-10-07T12:30", "neededMinutes": 210, "availableMinutes": 180},
    ]


def test_overdue_task_is_always_flagged():
    report = check_overload(day([task("late", 1, "2026-10-06T23:59")]))
    assert [w["taskId"] for w in report["deadlineWarnings"]] == ["late"]


def test_no_time_at_all():
    report = check_overload(day([task("A", 1)], planFrom="17:30"))
    assert (report["availableMinutes"], report["slackRatio"], report["overloaded"]) == (0, None, True)


def test_bad_range_is_refused():
    with pytest.raises(EngineError, match="low ≤ estimatedHours ≤ high"):
        check_overload(day([task("A", 2, estimatedHoursHigh=1)]))


def test_the_mvd_path_is_unchanged():
    data = scenario("S1")["input"]
    before = generate_mvd(copy.deepcopy(data))
    check_overload({k: v for k, v in data.items() if k != "disruption"})
    assert generate_mvd(copy.deepcopy(data)) == before
