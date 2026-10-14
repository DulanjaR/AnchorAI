import copy

import pytest

from components.c1_disruption.engine.diff import diff_plans
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.tests.golden.loader import scenario


def test_the_same_plan_has_no_changes():
    mvd = generate_mvd(scenario("S3")["input"])
    assert diff_plans(mvd, mvd) == {"changed": [], "total": 4, "changeRate": 0.0}


def test_reports_tags_that_differ_with_before_and_after():
    data = scenario("S3")["input"]
    default = generate_mvd(data)
    strict = generate_mvd({**copy.deepcopy(data), "strategy": {"compressRatio": 0.25}})
    result = diff_plans(default, strict)
    assert result["changed"] == [{"taskId": "D3", "before": "Reduce", "after": "Move"}]
    assert result["total"] == 4
    assert result["changeRate"] == 0.25


def test_slot_changes_alone_are_not_tag_changes():
    a = generate_mvd(scenario("S1")["input"])
    b = copy.deepcopy(a)
    b["tasks"][0]["start"], b["tasks"][0]["end"] = "10:00", "12:00"
    assert diff_plans(a, b)["changed"] == []


def test_plans_with_different_tasks_cannot_be_compared():
    with pytest.raises(EngineError, match="same tasks"):
        diff_plans(generate_mvd(scenario("S1")["input"]), generate_mvd(scenario("S2")["input"]))


def test_empty_plans():
    data = {**scenario("S1")["input"], "tasks": []}
    assert diff_plans(generate_mvd(data), generate_mvd(data)) == {"changed": [], "total": 0, "changeRate": 0.0}
