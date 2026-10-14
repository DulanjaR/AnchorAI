"""Metrics on golden scenarios, where every number can be checked by hand."""
import copy

import pytest

from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.metrics import plan_metrics as m
from components.c1_disruption.metrics.records import task_outcomes
from components.c1_disruption.tests.api.client import setup
from components.c1_disruption.tests.golden.loader import load_scenarios, scenario


def mvd_of(scenario_id, **strategy):
    data = copy.deepcopy(scenario(scenario_id)["input"])
    if strategy:
        data["strategy"] = strategy
    return generate_mvd(data)


class TestCtrr:
    def test_s1_both_critical_tasks_are_kept(self):
        # T1, T2 High + due today (critical); T3 Medium → not critical.
        assert m.ctrr_planned(mvd_of("S1")) == 1.0

    def test_s2_one_of_two_critical_tasks_is_moved(self):
        # D1 (High, today) Move, A1 (High, today) Keep; A2 Low.
        assert m.ctrr_planned(mvd_of("S2")) == 0.5

    def test_realised_counts_only_done(self):
        assert m.ctrr_realised(mvd_of("S1"), {"T1": "done", "T2": "partial"}) == 0.5

    def test_no_critical_tasks_is_undefined_not_zero(self):
        mvd = {"tasks": [{"id": "x", "priority": "Low", "daysUntilDeadline": 5, "tag": "Move"}]}
        assert m.ctrr_planned(mvd) is None


class TestPtvr:
    @pytest.mark.parametrize("s", [s for s in load_scenarios() if "error" not in s["expected"]], ids=lambda s: s["id"])
    def test_every_golden_plan_has_ptvr_zero(self, s):
        assert m.ptvr(generate_mvd(s["input"]), s["input"]["protectedBlocks"]) == 0

    def test_a_planted_overlap_is_measured(self):
        data = scenario("S1")["input"]
        mvd = copy.deepcopy(generate_mvd(data))
        mvd["tasks"][0]["start"], mvd["tasks"][0]["end"] = "12:00", "13:00"  # into lunch 12:30–13:30
        assert m.ptvr(mvd, data["protectedBlocks"]) == pytest.approx(1 / 3)


class TestFeasibility:
    def test_raw_estimates_always_fit_the_plan_made_from_them(self):
        raw = {t["id"]: t["estimatedHours"] for t in scenario("S3")["input"]["tasks"]}
        assert m.feasibility(mvd_of("S3"), raw) == 1.0

    def test_corrected_durations_on_the_same_event(self):
        # Placed: D1 09–11 (120), A1 13–15 (120), D3 11–12 (60). A1 really needs 5 h:
        # 300 × 0.5 = 150 > 120 → does not fit. Others fit.
        corrected = {"D1": 2.5, "A1": 5, "D2": 1, "D3": 2}
        assert m.feasibility(mvd_of("S3"), corrected) == pytest.approx(2 / 3)

    def test_realised_feasibility_uses_actual_minutes(self):
        # S1 slots: T1 09–11 (120), T2 13:30–15 (90), T3 15–17 (120).
        assert m.realised_feasibility(mvd_of("S1"), {"T1": 130, "T2": 80, "T3": None}) == 0.5

    def test_plan_completion_rate(self):
        assert m.plan_completion_rate(mvd_of("S1"), {"T1": "done", "T2": "partial"}) == pytest.approx(1 / 3)


class TestDecisions:
    def test_decision_change_rate(self):
        assert m.decision_change_rate(mvd_of("S3"), mvd_of("S3", compressRatio=0.25)) == 0.25

    def test_acceptance(self):
        assert m.acceptance(["accept", "edit", "reject", "accept"]) == {
            "accepted": 0.5, "acceptedOrEdited": 0.75, "decided": 4,
        }
        assert m.acceptance([]) == {"accepted": None, "acceptedOrEdited": None, "decided": 0}

    def test_edits_per_mvd(self):
        feedback = [
            {"action": "edit", "edits": [{"taskId": "a"}, {"taskId": "b"}]},
            {"action": "edit", "edits": [{"taskId": "c"}]},
            {"action": "accept", "edits": None},
            {"action": "reject", "edits": None},
        ]
        assert m.edits_per_mvd(feedback) == {"perEditedMvd": 1.5, "perDecidedMvd": 0.75}

    def test_time_to_decision(self):
        assert m.time_to_decision([30, 90, None, 60]) == {"mean": 60, "median": 60, "n": 3}


class TestSlack:
    def test_tight_slack_threshold(self):
        assert m.is_tight_slack(0.05) and not m.is_tight_slack(0.10) and not m.is_tight_slack(0.5)

    def test_no_available_time_is_tight(self):
        assert m.is_tight_slack(None)


def test_carry_over_metrics_wait_for_d_move():
    with pytest.raises(NotImplementedError, match="D-MOVE"):
        m.carry_over_placement_rate()


def test_task_outcomes_from_stored_records():
    ctx = setup("2026-10-07T09:00")
    ctx.call("PUT", "/api/me/settings", body={"workStart": "09:00", "workEnd": "18:00"})
    task = {"type": "Analog", "priority": "High", "estimatedHours": 1, "deadline": "2026-10-07T23:59",
            "plannedDate": "2026-10-07"}
    a = ctx.call("POST", "/api/tasks", body={**task, "title": "A"}).json()
    b = ctx.call("POST", "/api/tasks", body={**task, "title": "B"}).json()
    report = ctx.call("POST", "/api/disruptions", body={
        "date": "2026-10-07", "type": "transport_delay", "start": "09:00", "timeLostMinutes": 60, "severity": 1,
        "confirmed": True,
    }).json()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    ctx.call("POST", f"/api/tasks/{a['id']}/start")
    ctx.clock.set("2026-10-07T10:10")
    ctx.call("POST", f"/api/tasks/{a['id']}/done")
    ctx.call("POST", "/api/reviews/2026-10-07", body={"items": [{"taskId": b["id"], "outcome": "not_done"}]})
    outcomes, actual = task_outcomes(ctx.store, ctx.store.get("mvds", mvd["id"]))
    assert outcomes == {a["id"]: "done", b["id"]: "not_done"}
    assert actual == {a["id"]: 70, b["id"]: None}
