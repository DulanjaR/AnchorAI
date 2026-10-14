"""OVERRUN_RISK (planning chat, 14 Oct 2026): the high duration estimate is only used
for this warning; Fi, fit check, slot length and compression % use the point."""
import copy

import pytest

from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.tests.golden.loader import load_scenarios, scenario

PLANS = [s for s in load_scenarios() if "error" not in s["expected"]]


def with_high(scenario_id: str, highs: dict[str, float]) -> dict:
    data = copy.deepcopy(scenario(scenario_id)["input"])
    for t in data["tasks"]:
        if t["id"] in highs:
            t["estimatedHoursHigh"] = highs[t["id"]]
    return data


def overruns(mvd: dict) -> dict[str, str]:
    return {w["taskId"]: w["message"] for w in mvd["warnings"] if w["code"] == "OVERRUN_RISK"}


@pytest.mark.parametrize("s", PLANS, ids=[s["id"] for s in PLANS])
def test_a_wide_range_changes_nothing_but_the_overrun_warnings(s):
    data = copy.deepcopy(s["input"])
    for t in data["tasks"]:
        t["estimatedHoursHigh"] = t["estimatedHours"] * 3
    with_range, plain = generate_mvd(data), generate_mvd(s["input"])
    assert with_range["tasks"] == plain["tasks"]  # point estimate decides everything
    assert [w for w in with_range["warnings"] if w["code"] != "OVERRUN_RISK"] == plain["warnings"]
    keep = {t["id"] for t in plain["tasks"] if t["tag"] == "Keep"}
    assert set(overruns(with_range)) <= keep  # only Keep tasks can get it


def test_crossing_the_next_fixed_block():
    # S1 T1 Keep 09:00–11:00; the free stretch ends at lunch 12:30. High 4 h → 13:00.
    mvd = generate_mvd(with_high("S1", {"T1": 4}))
    assert overruns(mvd) == {"T1": "Overrun risk: it is planned 09:00–11:00, but if it takes as long as the high "
                                   "estimate (240 min) it would run into Lunch at 12:30."}


def test_crossing_the_end_of_the_window():
    # S1 T3 Keep 15:00–17:00; free time ends at 18:00. High 3.5 h → 18:30.
    assert "the end of today's free time at 18:00" in overruns(generate_mvd(with_high("S1", {"T3": 3.5})))["T3"]


def test_crossing_an_unavailable_disruption_window():
    # S15 D1 Keep 09:00–12:00; urgent work takes 13:00–15:00. High 4.5 h → 13:30.
    assert "urgent work (13:00–15:00) at 13:00" in overruns(generate_mvd(with_high("S15", {"D1": 4.5})))["D1"]


def test_no_warning_when_the_high_estimate_still_fits():
    # S1 T1 high 3.5 h → 12:30 exactly: fits; T2 13:30–15:00 high 1.6 h → 15:06 < 18:00.
    assert overruns(generate_mvd(with_high("S1", {"T1": 3.5, "T2": 1.6}))) == {}


def test_reduce_and_move_tasks_never_get_it():
    # S3: D3 Reduce, D2 Move.
    assert overruns(generate_mvd(with_high("S3", {"D3": 10, "D2": 10}))) == {}


def test_without_a_high_estimate_there_is_no_overrun_warning():
    for s in PLANS:
        assert overruns(generate_mvd(s["input"])) == {}


def test_compression_is_measured_from_the_point():
    # S3 D3: 60 of 90 point minutes → 33.3 %, whatever the high estimate.
    d3 = next(t for t in generate_mvd(with_high("S3", {"D3": 4}))["tasks"] if t["id"] == "D3")
    assert d3["compressionPct"] == 33.3
