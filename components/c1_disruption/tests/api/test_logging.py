"""Logging for the evaluation (docs/METHODOLOGY.md §6) and the ML hooks."""
from dataclasses import dataclass

from components.c1_disruption.app.services.planning import STRATEGIES, Correction, Ranking
from components.c1_disruption.tests.api.client import setup

DATE = "2026-10-07"


def ready_day(**hooks):
    ctx = setup(f"{DATE}T09:00", **hooks)
    ctx.call("PUT", "/api/me/settings", body={"workStart": "09:00", "workEnd": "18:00"})
    ctx.call("POST", "/api/protected-blocks", body={"label": "Lunch", "start": "12:30", "end": "13:30"})
    task = {"type": "Analog", "priority": "High", "estimatedHours": 2, "deadline": f"{DATE}T23:59", "plannedDate": DATE}
    reading = ctx.call("POST", "/api/tasks", body={**task, "title": "Reading"}).json()
    coding = ctx.call("POST", "/api/tasks", body={**task, "title": "Coding", "type": "Digital", "estimatedHours": 1.5}).json()
    report = ctx.call("POST", "/api/disruptions", body={
        "date": DATE, "type": "power_outage", "start": "09:00", "timeLostMinutes": 180, "severity": 2, "confirmed": True,
    }).json()
    return ctx, reading, coding, report


def test_default_mvd_logs_fixed_order_model_off_and_estimates():
    ctx, reading, coding, report = ready_day()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    assert mvd["policyMode"] == "fixed_order"
    assert mvd["shownPolicy"] == "fixed_order"
    assert mvd["rankingShown"] == list(STRATEGIES)
    assert mvd["strategyId"] == "default"
    assert mvd["strategy"] == {"compressRatio": 0.5}
    assert mvd["modelOn"] is False
    assert mvd["manualReplanFirst"] is False
    assert mvd["timeToDecisionSeconds"] is None
    assert mvd["taskLog"] == [
        {"taskId": reading["id"], "estimatedHours": 2, "correctedHours": 2, "correctedLowHours": 2,
         "correctedHighHours": 2, "correctionSource": "fallback"},
        {"taskId": coding["id"], "estimatedHours": 1.5, "correctedHours": 1.5, "correctedLowHours": 1.5,
         "correctedHighHours": 1.5, "correctionSource": "fallback"},
    ]


def test_manual_replan_first_is_logged():
    ctx, _, coding, report = ready_day()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd",
                   body={"manualReplan": [{"taskId": coding["id"], "tag": "Move"}]}).json()
    assert mvd["manualReplanFirst"] is True


def test_time_to_decision_and_tag_changes_on_edit():
    ctx, _, coding, report = ready_day()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    ctx.clock.set(f"{DATE}T09:02")  # the student decides 2 minutes later
    edited = ctx.call("POST", f"/api/mvds/{mvd['id']}/edit", body={"changes": [{"taskId": coding["id"], "tag": "Move"}]}).json()
    assert edited["timeToDecisionSeconds"] == 120
    (fb,) = ctx.store.list("feedback")
    assert fb["tagChanges"] == [{"taskId": coding["id"], "before": "Keep", "after": "Move"}]
    assert (fb["totalTasks"], fb["timeToDecisionSeconds"]) == (2, 120)


def test_slot_only_edit_has_no_tag_changes_and_accept_reject_have_none():
    ctx, _, coding, report = ready_day()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    ctx.call("POST", f"/api/mvds/{mvd['id']}/edit", body={"changes": [{"taskId": coding["id"], "start": "15:00", "end": "16:30"}]})
    for action in ("accept", "reject"):
        mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
        ctx.call("POST", f"/api/mvds/{mvd['id']}/{action}")
    assert [f["tagChanges"] for f in ctx.store.list("feedback")] == [[], [], []]


@dataclass
class HalfHourMore:
    """A fake Model 1: every task takes 30 min longer, range ±30 min."""

    model_on: bool = True

    def correct(self, user_id, task, context):
        point = task["estimatedHours"] + 0.5
        return Correction(point, point - 0.5, point + 0.5, "model")


def test_a_drift_model_feeds_the_engine_and_is_logged():
    ctx, reading, _, report = ready_day(corrector=HalfHourMore())
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    assert mvd["modelOn"] is True
    first = next(t for t in mvd["plan"]["tasks"] if t["id"] == reading["id"])
    assert first["estimatedHours"] == 2.5  # the engine planned with the corrected point
    assert (first["start"], first["end"]) == ("09:00", "11:30")
    log = next(e for e in mvd["taskLog"] if e["taskId"] == reading["id"])
    assert (log["estimatedHours"], log["correctedHours"], log["correctedLowHours"], log["correctedHighHours"]) == (2, 2.5, 2, 3)
    assert log["correctionSource"] == "model"


@dataclass
class StrictFirst:
    """A fake Model 2 that ranks a no-shortening strategy first."""

    def rank(self, user_id, context):
        return Ranking(policy_mode="bandit", ranking=["no_shortening", "default"], shown_policy="bandit")


def test_a_strategy_chooser_shapes_the_mvd_and_is_logged(monkeypatch):
    from components.c1_disruption.app.services import planning

    monkeypatch.setitem(planning.STRATEGIES, "no_shortening", {"compressRatio": 0})
    ctx, _, _, report = ready_day(chooser=StrictFirst())
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    assert (mvd["policyMode"], mvd["rankingShown"], mvd["strategyId"]) == ("bandit", ["no_shortening", "default"], "no_shortening")
    assert mvd["strategy"] == {"compressRatio": 0}
    assert mvd["input"]["strategy"] == {"compressRatio": 0}
