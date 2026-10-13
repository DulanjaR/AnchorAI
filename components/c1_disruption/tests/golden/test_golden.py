"""Runs the frozen golden scenarios S1–S16 against the Python engine.

The approved fields were hand-worked by the owner BEFORE the Node engine existed;
explanation text and the other captured fields come from the approved Node engine.
Everything must match exactly (fi after rounding to 3 decimals, rule R12).
"""
import re

import pytest

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.jsnum import to_fixed_number
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.tests.engine.invariants import compute_ptvr, find_violations
from components.c1_disruption.tests.golden.loader import (
    APPROVED_TASK_FIELDS,
    CAPTURED_TASK_FIELDS,
    load_scenarios,
)

SCENARIOS = load_scenarios()
PLANS = [s for s in SCENARIOS if "error" not in s["expected"]]
ERRORS = [s for s in SCENARIOS if "error" in s["expected"]]
TASK_CASES = [(s, task_id) for s in PLANS for task_id in s["expected"]["tasks"]]


def test_all_sixteen_scenarios_are_present():
    assert [s["id"] for s in SCENARIOS] == [f"S{i}" for i in range(1, 17)]


@pytest.mark.parametrize(("scenario", "task_id"), TASK_CASES, ids=[f"{s['id']}-{t}" for s, t in TASK_CASES])
def test_task(scenario, task_id):
    expected = scenario["expected"]["tasks"][task_id]
    got = next(t for t in generate_mvd(scenario["input"])["tasks"] if t["id"] == task_id)
    assert to_fixed_number(got["fi"], 3) == expected["fi"]
    fields = [f for f in APPROVED_TASK_FIELDS + CAPTURED_TASK_FIELDS if f != "fi"]
    assert {f: got[f] for f in fields} == {f: expected[f] for f in fields}


@pytest.mark.parametrize("scenario", PLANS, ids=[s["id"] for s in PLANS])
def test_plan_level_fields(scenario):
    expected = scenario["expected"]
    mvd = generate_mvd(scenario["input"])
    assert [t["id"] for t in mvd["tasks"]] == expected["order"]
    assert mvd["horizon"] == expected["horizon"]
    assert mvd["disruption"]["kind"] == expected["disruptionKind"]
    assert mvd["freeMinutesLeft"] == expected["freeMinutesLeft"]
    assert mvd["warnings"] == expected["warnings"]


@pytest.mark.parametrize("scenario", PLANS, ids=[s["id"] for s in PLANS])
def test_protected_blocks_returned_unchanged(scenario):
    protect = {
        p["id"]: {k: p[k] for k in ("tag", "start", "end", "reason", "explanation")}
        for p in generate_mvd(scenario["input"])["protect"]
    }
    assert protect == scenario["expected"]["protect"]


@pytest.mark.parametrize("scenario", PLANS, ids=[s["id"] for s in PLANS])
def test_ptvr_zero_and_hard_rules(scenario):
    mvd = generate_mvd(scenario["input"])
    assert compute_ptvr(mvd, scenario["input"]) == 0
    assert find_violations(mvd, scenario["input"]) == []


@pytest.mark.parametrize("scenario", ERRORS, ids=[s["id"] for s in ERRORS])
def test_raises_clear_error(scenario):
    expected = scenario["expected"]["error"]
    with pytest.raises(EngineError) as err:
        generate_mvd(scenario["input"])
    assert re.search(expected["messageRegex"], str(err.value))
    assert str(err.value) == expected["message"]
