"""End-to-end: every golden scenario is replayed through the HTTP API
(settings → protected blocks → tasks → confirmed disruption → generate → accept)
and must give exactly the golden result. This proves the API passes the user's
data to the engine without changing it, and that the finalised plan written to
the tasks keeps PTVR = 0. Port of the Node goldenFlow.test.js, comparing every
field (the Node test compared tag, slot, reason and deadline risk).
"""
import re

import pytest

from components.c1_disruption.engine.jsnum import to_fixed_number
from components.c1_disruption.engine.time import MINUTES_PER_DAY, block_to_intervals, overlaps, to_minutes, Interval
from components.c1_disruption.tests.api.client import setup
from components.c1_disruption.tests.golden.loader import APPROVED_TASK_FIELDS, CAPTURED_TASK_FIELDS, load_scenarios

SCENARIOS = load_scenarios()


def time_lost(disruption: dict) -> int:
    """The API takes "time lost"; the scenarios give start/end. A window crossing
    midnight (S14: 20:00–02:00) is 6 h lost."""
    return (to_minutes(disruption["end"]) - to_minutes(disruption["start"]) + MINUTES_PER_DAY) % MINUTES_PER_DAY


def replay(scenario: dict):
    data = scenario["input"]
    ctx = setup(f"{data['date']}T{data['planFrom']}")
    ctx.call("PUT", "/api/me/settings", body={"workStart": data["workHours"]["start"], "workEnd": data["workHours"]["end"]})
    block_ids = {}  # API id → scenario id
    for b in data["protectedBlocks"]:
        res = ctx.call("POST", "/api/protected-blocks", body={"label": b["label"], "start": b["start"], "end": b["end"]})
        block_ids[res.json()["id"]] = b["id"]
    task_ids = {}  # API id → scenario id
    for t in data["tasks"]:
        res = ctx.call("POST", "/api/tasks", body={
            "title": t["title"], "type": t["type"], "priority": t["priority"], "estimatedHours": t["estimatedHours"],
            "deadline": t["deadline"], "delegable": t["delegable"], "plannedDate": data["date"],
        })
        assert res.status_code == 201, res.json()
        task_ids[res.json()["id"]] = t["id"]
    report = ctx.call("POST", "/api/disruptions", body={
        "date": data["date"], "type": data["disruption"]["type"], "start": data["disruption"]["start"],
        "timeLostMinutes": time_lost(data["disruption"]), "severity": 2, "confirmed": True,
    })
    assert report.status_code == 201, report.json()
    mvd = ctx.call("POST", f"/api/disruptions/{report.json()['id']}/mvd", body={"planFrom": data["planFrom"]})
    return ctx, task_ids, block_ids, mvd


PLANS = [s for s in SCENARIOS if "error" not in s["expected"]]
ERRORS = [s for s in SCENARIOS if "error" in s["expected"]]


@pytest.mark.parametrize("scenario", PLANS, ids=[s["id"] for s in PLANS])
def test_same_plan_as_the_golden_spec_and_accepted_plan_keeps_ptvr_zero(scenario):
    expected = scenario["expected"]
    ctx, task_ids, block_ids, res = replay(scenario)
    assert res.status_code == 201, res.json()
    plan = res.json()["plan"]

    assert [task_ids[t["id"]] for t in plan["tasks"]] == expected["order"]
    fields = [f for f in APPROVED_TASK_FIELDS + CAPTURED_TASK_FIELDS if f != "fi"]
    for t in plan["tasks"]:
        want = expected["tasks"][task_ids[t["id"]]]
        assert to_fixed_number(t["fi"], 3) == want["fi"]
        assert {f: t[f] for f in fields} == {f: want[f] for f in fields}, task_ids[t["id"]]
    assert plan["freeMinutesLeft"] == expected["freeMinutesLeft"]
    assert plan["horizon"] == expected["horizon"]
    assert plan["disruption"]["kind"] == expected["disruptionKind"]
    assert [w["message"] for w in plan["warnings"]] == [w["message"] for w in expected["warnings"]]
    assert {
        block_ids[p["id"]]: {k: p[k] for k in ("tag", "start", "end", "reason", "explanation")} for p in plan["protect"]
    } == expected["protect"]

    # Accept, then check the plan stored on the tasks against the protected blocks.
    accepted = ctx.call("POST", f"/api/mvds/{res.json()['id']}/accept")
    assert accepted.status_code == 200
    tasks = ctx.call("GET", f"/api/tasks?date={scenario['input']['date']}").json()
    blocks = [iv for b in scenario["input"]["protectedBlocks"] for iv in block_to_intervals(b)]
    violations = [
        t["id"] for t in tasks
        if t["mvdStart"] and any(overlaps(Interval(to_minutes(t["mvdStart"]), to_minutes(t["mvdEnd"])), b) for b in blocks)
    ]
    assert violations == []  # PTVR = 0 on the finalised plan
    assert all(t["mvdTag"] == expected["tasks"][task_ids[t["id"]]]["tag"] for t in tasks)


@pytest.mark.parametrize("scenario", ERRORS, ids=[s["id"] for s in ERRORS])
def test_engine_error_is_422_with_the_golden_message(scenario):
    _, _, _, res = replay(scenario)
    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "CANNOT_PLAN"
    assert error["message"] == scenario["expected"]["error"]["message"]
    assert re.search(scenario["expected"]["error"]["messageRegex"], error["message"])
