"""Edge cases for generate_mvd that the golden scenarios do not cover."""
import copy

import pytest

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.tests.engine.invariants import find_violations
from components.c1_disruption.tests.golden.loader import scenario


def base_input(**over):
    return {
        "date": "2026-10-07",
        "workHours": {"start": "09:00", "end": "17:00"},
        "planFrom": "09:00",
        "disruption": {"type": "power_outage", "start": "09:00", "end": "11:00"},
        "protectedBlocks": [{"id": "lunch", "label": "Lunch", "start": "12:00", "end": "13:00"}],
        "tasks": [
            {"id": "T1", "title": "Write code", "type": "Digital", "priority": "High", "estimatedHours": 2,
             "deadline": "2026-10-07T23:59", "delegable": False},
            {"id": "T2", "title": "Read notes", "type": "Analog", "priority": "Medium", "estimatedHours": 1,
             "deadline": "2026-10-08T23:59", "delegable": False},
        ],
        **over,
    }


def test_is_pure_input_unchanged_and_same_output_twice():
    data = base_input()
    before = copy.deepcopy(data)
    first = generate_mvd(data)
    assert data == before
    assert generate_mvd(data) == first


def test_output_does_not_share_the_input_disruption_dict():
    data = base_input()
    mvd = generate_mvd(data)
    mvd["disruption"]["start"] = "00:00"
    assert data["disruption"]["start"] == "09:00"


def test_every_task_gets_a_tag_a_reason_and_an_explanation():
    for t in generate_mvd(base_input())["tasks"]:
        assert t["tag"] in {"Keep", "Reduce", "Move", "Delegate"}
        assert t["reason"].replace("_", "").isupper()
        assert t["explanation"]


def test_no_tasks_gives_an_empty_plan_with_protected_blocks():
    mvd = generate_mvd(base_input(tasks=[]))
    assert mvd["tasks"] == []
    assert len(mvd["protect"]) == 1


def test_missing_delegable_means_not_delegable():
    data = base_input()
    for t in data["tasks"]:
        del t["delegable"]
    assert all(t["delegable"] is False for t in generate_mvd(data)["tasks"])


def test_replanning_after_work_hours_places_nothing_and_warns():
    mvd = generate_mvd(base_input(planFrom="17:30"))
    assert all(t["start"] is None for t in mvd["tasks"])
    assert [w["taskId"] for w in mvd["warnings"]] == ["T1", "T2"]


def test_a_task_longer_than_the_window_falls_back_to_the_gap_start():
    # Q6 revision, step b.
    data = base_input(
        disruption={"type": "transport_delay", "start": "10:00", "end": "11:00"},
        protectedBlocks=[],
        tasks=[{"id": "A", "title": "Long reading", "type": "Analog", "priority": "High", "estimatedHours": 3,
                "deadline": "2026-10-07T23:59"}],
    )
    (t,) = generate_mvd(data)["tasks"]
    assert (t["start"], t["end"]) == ("09:00", "12:00")


def test_a_protected_block_covering_the_whole_day_leaves_no_free_time():
    mvd = generate_mvd(base_input(protectedBlocks=[{"id": "all", "label": "Exam", "start": "08:00", "end": "18:00"}]))
    assert all(t["tag"] == "Move" for t in mvd["tasks"])


def test_an_overnight_protected_block_inside_work_hours_is_respected():
    # Night-shift worker.
    data = base_input(
        workHours={"start": "00:00", "end": "23:59"},
        planFrom="00:00",
        disruption={"type": "transport_delay", "start": "07:00", "end": "08:00"},
        protectedBlocks=[{"id": "sleep", "label": "Sleep", "start": "22:00", "end": "06:00"}],
    )
    mvd = generate_mvd(data)
    assert find_violations(mvd, data) == []
    assert all(t["start"] >= "06:00" for t in mvd["tasks"])


def test_a_none_ef_for_any_task_raises_even_one_that_would_use_ef_1():
    data = base_input(tasks=[{"id": "M", "title": "Team call", "type": "Meeting", "priority": "High",
                              "estimatedHours": 1, "deadline": "2026-10-07T23:59"}])
    with pytest.raises(EngineError, match=r"power_outage[\s\S]*Meeting"):
        generate_mvd(data)


def test_low_urgency_offers_starting_early_only_when_free_time_is_left():
    s2 = generate_mvd(scenario("S2")["input"])  # A2 moved, plenty of free time left
    assert s2["freeMinutesLeft"] > 0
    a2 = next(t for t in s2["tasks"] if t["id"] == "A2")
    assert "You have free time today, so you can start it early if you like." in a2["explanation"]

    s7 = generate_mvd(scenario("S7")["input"])  # L1, L2 moved, day fully used
    assert s7["freeMinutesLeft"] == 0
    l1 = next(t for t in s7["tasks"] if t["id"] == "L1")
    assert "start it early" not in l1["explanation"]


def test_compression_pct_rounds_halves_up_like_node():
    # 225 of 240 min: 1000 × (1 − 225/240) = 62.5 → Node 6.3; Python's round() would give 6.2.
    # Expected values printed by the Node engine (13 Oct 2026).
    data = base_input(
        workHours={"start": "09:00", "end": "12:45"},
        disruption={"type": "urgent_work", "start": "13:00", "end": "14:00"},
        protectedBlocks=[],
        tasks=[{"id": "A", "title": "Essay", "type": "Digital", "priority": "High", "estimatedHours": 4,
                "deadline": "2026-10-07T23:59"}],
    )
    (t,) = generate_mvd(data)["tasks"]
    assert (t["tag"], t["start"], t["end"], t["compressionPct"]) == ("Reduce", "09:00", "12:45", 6.3)
    assert t["explanation"] == (
        "Shortened by 6.3% to fit the free time left today (09:00–12:45). "
        "Do the most important part first (Fi 0.125)."
    )


def test_tasks_come_back_in_placement_order():
    groups = [t["group"] for t in generate_mvd(base_input())["tasks"]]
    assert sorted(groups) == groups


class TestUnavailableDisruptions:
    """Task 2a."""

    @staticmethod
    def day(**over):
        return base_input(**{
            "disruption": {"type": "urgent_work", "start": "09:00", "end": "11:00"},
            "protectedBlocks": [],
            **over,
        })

    def test_nothing_is_placed_inside_the_window(self):
        # Even an Analog task that window-first would put there.
        data = self.day(tasks=[{"id": "A", "title": "Reading", "type": "Analog", "priority": "High",
                                "estimatedHours": 2, "deadline": "2026-10-07T23:59"}])
        mvd = generate_mvd(data)
        assert (mvd["tasks"][0]["start"], mvd["tasks"][0]["end"]) == ("11:00", "13:00")
        assert mvd["disruption"]["kind"] == "unavailable"
        assert find_violations(mvd, data) == []

    def test_meeting_and_fixed_need_no_ef_value(self):
        data = self.day(
            disruption={"type": "health_issue", "start": "09:00", "end": "11:00"},
            tasks=[
                {"id": "M", "title": "Group call", "type": "Meeting", "priority": "High", "estimatedHours": 1,
                 "deadline": "2026-10-07T23:59"},
                {"id": "F", "title": "Lab session", "type": "Fixed", "priority": "Medium", "estimatedHours": 1,
                 "deadline": "2026-10-08T23:59"},
            ],
        )
        assert [t["efUsed"] for t in generate_mvd(data)["tasks"]] == [1.0, 1.0]

    def test_an_unknown_task_type_still_raises(self):
        data = self.day(tasks=[{"id": "X", "title": "Gaming", "type": "Gaming", "priority": "High",
                                "estimatedHours": 1, "deadline": "2026-10-07T23:59"}])
        with pytest.raises(EngineError, match="Gaming"):
            generate_mvd(data)

    def test_a_window_crossing_midnight_is_clipped_too(self):
        data = self.day(
            workHours={"start": "16:00", "end": "23:00"},
            planFrom="16:00",
            disruption={"type": "family_obligation", "start": "19:00", "end": "01:00"},
            tasks=[{"id": "A", "title": "Essay", "type": "Digital", "priority": "High", "estimatedHours": 4,
                    "deadline": "2026-10-07T23:59"}],
        )
        (t,) = generate_mvd(data)["tasks"]
        # Only 16:00–19:00 is free: 180 of 240 min → Reduce 25%.
        assert (t["tag"], t["start"], t["end"], t["compressionPct"]) == ("Reduce", "16:00", "19:00", 25)


def test_unknown_disruption_type_raises():
    with pytest.raises(EngineError, match="alien_invasion"):
        generate_mvd(base_input(disruption={"type": "alien_invasion", "start": "09:00", "end": "10:00"}))
