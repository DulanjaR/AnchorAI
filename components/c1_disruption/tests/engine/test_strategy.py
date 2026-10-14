"""Strategy config and duration range (methodology update, 14 Oct 2026).

Hard rule: with defaults the output is identical to the golden spec.
"""
import copy
import random

import pytest

from components.c1_disruption.engine import config
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.explain import shortening_text
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.engine.strategy import read_strategy
from components.c1_disruption.tests.engine.invariants import find_violations
from components.c1_disruption.tests.engine.test_stress import SEED, random_day, seeded_random
from components.c1_disruption.tests.golden.loader import load_scenarios, scenario

PLANS = [s for s in load_scenarios() if "error" not in s["expected"]]


def with_strategy(data: dict, **strategy) -> dict:
    return {**copy.deepcopy(data), "strategy": strategy}


# --- defaults preserve the golden spec -----------------------------------------

@pytest.mark.parametrize("s", PLANS, ids=[s["id"] for s in PLANS])
def test_explicit_default_strategy_gives_the_golden_output(s):
    assert generate_mvd(with_strategy(s["input"], compressRatio=config.MAX_COMPRESSION)) == generate_mvd(s["input"])
    assert generate_mvd({**s["input"], "strategy": {}}) == generate_mvd(s["input"])


@pytest.mark.parametrize("s", PLANS, ids=[s["id"] for s in PLANS])
def test_a_range_equal_to_the_point_gives_the_golden_output(s):
    data = copy.deepcopy(s["input"])
    for t in data["tasks"]:
        t["estimatedHoursLow"] = t["estimatedHours"]
        t["estimatedHoursHigh"] = t["estimatedHours"]
    assert generate_mvd(data) == generate_mvd(s["input"])


def test_fi_and_placement_use_the_point_value_not_the_range():
    data = copy.deepcopy(scenario("S3")["input"])
    for t in data["tasks"]:
        t["estimatedHoursLow"] = t["estimatedHours"] * 0.5
        t["estimatedHoursHigh"] = t["estimatedHours"] * 3
    assert generate_mvd(data)["tasks"] == generate_mvd(scenario("S3")["input"])["tasks"]


def test_default_is_the_config_value():
    assert read_strategy(None).compress_ratio == config.MAX_COMPRESSION == 0.5


# --- compressRatio changes what may be shortened --------------------------------

def _task(mvd: dict, task_id: str) -> dict:
    return next(t for t in mvd["tasks"] if t["id"] == task_id)


def test_s3_d3_needs_33_percent_so_it_is_moved_when_only_25_percent_is_allowed():
    # Golden S3: D3 (90 min) is shortened to the 60-min gap = 33.3%.
    d3 = _task(generate_mvd(with_strategy(scenario("S3")["input"], compressRatio=0.25)), "D3")
    assert (d3["tag"], d3["reason"], d3["start"], d3["deadlineRisk"]) == ("Move", "BUDGET_EXCEEDED", None, True)
    assert d3["explanation"] == (
        "Moved to tomorrow: there is not enough free time left today, even shortened by 25%. "
        "Warning: this task is due tomorrow, so its deadline is at risk."
    )


def test_s3_d3_is_still_reduced_when_40_percent_is_allowed():
    d3 = _task(generate_mvd(with_strategy(scenario("S3")["input"], compressRatio=0.4)), "D3")
    assert (d3["tag"], d3["start"], d3["end"], d3["compressionPct"]) == ("Reduce", "11:00", "12:00", 33.3)


def test_ratio_zero_never_shortens_anything():
    for s in PLANS:
        mvd = generate_mvd(with_strategy(s["input"], compressRatio=0))
        assert all(t["tag"] != "Reduce" for t in mvd["tasks"]), s["id"]


def test_ratio_zero_explanation_drops_the_shortening_clause():
    k1 = _task(generate_mvd(with_strategy(scenario("S5")["input"], compressRatio=0)), "K1")
    assert k1["explanation"].startswith("Moved to tomorrow: there is not enough free time left today. Warning:")


@pytest.mark.parametrize(
    ("ratio", "text"),
    [(0.5, ", even at half length."), (0, "."), (0.25, ", even shortened by 25%."), (0.3, ", even shortened by 30%.")],
)
def test_shortening_text(ratio, text):
    ctx = {"disruptionType": "power_outage", "windowStart": "09:00", "windowEnd": "12:00", "maxCompression": ratio}
    assert shortening_text(ctx) == text


def test_hard_rules_hold_for_500_random_days_with_random_ratios():
    rand = seeded_random(SEED)
    ratios = random.Random(14).choices([0, 0.1, 0.25, 0.3, 0.5, 0.75, 0.9], k=500)
    failures = []
    for i, ratio in enumerate(ratios):
        day = {**random_day(rand), "strategy": {"compressRatio": ratio}}
        problems = find_violations(generate_mvd(day), day)
        if problems:
            failures.append((i, ratio, problems))
    assert failures == []


@pytest.mark.parametrize(
    "strategy", [{"compressRatio": 1}, {"compressRatio": -0.1}, {"compressRatio": "0.5"}, {"compressRatio": True}]
)
def test_invalid_ratio_raises(strategy):
    with pytest.raises(EngineError, match="compressRatio"):
        generate_mvd({**scenario("S1")["input"], "strategy": strategy})


def test_unknown_strategy_setting_raises():
    with pytest.raises(EngineError, match="Unknown strategy setting"):
        generate_mvd({**scenario("S1")["input"], "strategy": {"compressRatoi": 0.3}})


# --- duration range validation ---------------------------------------------------

@pytest.mark.parametrize(
    ("low", "high", "message"),
    [
        (2.5, None, "low ≤ estimatedHours ≤ high"),  # low above the point (2 h)
        (None, 1.5, "low ≤ estimatedHours ≤ high"),  # high below the point
        (0, None, "'estimatedHoursLow' must be a positive number"),
        (None, "3", "'estimatedHoursHigh' must be a positive number"),
    ],
)
def test_invalid_duration_range_raises(low, high, message):
    data = copy.deepcopy(scenario("S1")["input"])
    data["tasks"][0].update(estimatedHoursLow=low, estimatedHoursHigh=high)
    with pytest.raises(EngineError, match=message):
        generate_mvd(data)
