from dataclasses import dataclass
from functools import cmp_to_key

import pytest

from components.c1_disruption.engine.classify import (
    compare_placement_order,
    group_for,
    has_deadline_risk,
    reason_for,
    tag_for,
)


class TestGroupFor:
    def test_low_fi_and_high_is_a(self):
        assert group_for(0.2, "High") == "A"

    def test_low_fi_and_not_high_is_b(self):
        assert group_for(0.2, "Medium") == "B"
        assert group_for(0.2, "Low") == "B"

    def test_fi_exactly_0_5_is_not_below_the_keep_threshold(self):
        assert group_for(0.5, "High") == "C"

    def test_up_to_and_including_2_is_c_above_is_d(self):
        assert group_for(2.0, "Low") == "C"
        assert group_for(2.0001, "Low") == "D"


@dataclass
class Item:
    id: str
    group: str = "A"
    fi: float = 0.3
    deadline_key: int = 100
    duration_minutes: int = 60


def sort_ids(items: list[Item]) -> list[str]:
    return [i.id for i in sorted(items, key=cmp_to_key(compare_placement_order))]


class TestPlacementOrder:
    def test_group_order_comes_first(self):
        items = [Item("c", group="C", fi=0.6), Item("a", fi=0.4), Item("b", group="B", fi=0.1)]
        assert sort_ids(items) == ["a", "b", "c"]

    def test_then_fi_ascending(self):
        assert sort_ids([Item("x", fi=0.4), Item("y", fi=0.2)]) == ["y", "x"]

    def test_fi_tie_within_float_noise_then_deadline_then_duration(self):
        fi = 1.0 / 0.7
        assert sort_ids([Item("late", fi=fi, deadline_key=200), Item("early", fi=fi + 1e-12, deadline_key=100)]) == [
            "early",
            "late",
        ]
        assert sort_ids([Item("long", duration_minutes=120), Item("short", duration_minutes=30)]) == ["short", "long"]


@pytest.mark.parametrize(
    ("outcome", "tag"),
    [
        ({"placed": True, "compressed": False, "delegable": False}, "Keep"),
        ({"placed": True, "compressed": False, "delegable": True}, "Keep"),  # delegable but fits → placed normally
        ({"placed": True, "compressed": True, "delegable": False}, "Reduce"),
        ({"placed": False, "compressed": False, "delegable": True}, "Delegate"),
        ({"placed": False, "compressed": False, "delegable": False}, "Move"),
    ],
)
def test_tag_by_outcome(outcome, tag):
    assert tag_for(**outcome) == tag


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"placed": True, "compressed": True, "blocked": True}, "REDUCE_BUDGET"),
        ({"placed": True, "blocked": True, "group": "A"}, "OUTSIDE_DISRUPTION_WINDOW"),
        ({"placed": True, "group": "A"}, "KEEP_URGENT"),
        ({"placed": True, "group": "B"}, "FITS_FULLY"),
        ({"placed": True, "group": "C"}, "FITS_FULLY"),
        ({"delegable": True, "blocked": True}, "DELEGABLE"),
        ({"blocked": True}, "BLOCKED_BY_DISRUPTION"),
        ({"group": "D"}, "LOW_URGENCY"),
        ({"group": "D", "time_taken": True}, "LOW_URGENCY"),  # never placed anyway, not "time taken"
        ({"time_taken": True}, "TIME_TAKEN_BY_DISRUPTION"),
        ({"time_taken": True, "delegable": True}, "DELEGABLE"),
        ({"placed": True, "time_taken": True}, "FITS_FULLY"),
        ({}, "BUDGET_EXCEEDED"),
    ],
)
def test_reason_for(over, reason):
    base = {"placed": False, "compressed": False, "blocked": False, "group": "C", "delegable": False}
    assert reason_for(**{**base, **over}) == reason


class TestDeadlineRisk:
    def test_move_due_today(self):
        assert has_deadline_risk(tag="Move", days_until_deadline=0, fi=3)

    def test_move_due_tomorrow_even_when_flexible(self):
        assert has_deadline_risk(tag="Move", days_until_deadline=1, fi=4)

    def test_move_urgent_fi_even_if_due_later(self):
        assert has_deadline_risk(tag="Move", days_until_deadline=2, fi=0.4)

    def test_move_flexible_due_in_two_days_or_more(self):
        assert not has_deadline_risk(tag="Move", days_until_deadline=2, fi=1.4)

    def test_delegate_never_carries_the_warning(self):
        assert not has_deadline_risk(tag="Delegate", days_until_deadline=0, fi=0.1)

    def test_placed_tasks_never_carry_the_warning(self):
        assert not has_deadline_risk(tag="Reduce", days_until_deadline=0, fi=0.1)
