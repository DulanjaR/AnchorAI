"""ML Model 1 on a SYNTHETIC fixture (tests/ml/fixtures.py): pipeline checks only."""
import copy

import numpy as np
import pytest

from components.c1_disruption.ml.drift import baselines
from components.c1_disruption.ml.drift.corrector import ModelCorrector
from components.c1_disruption.ml.drift.data import FEATURE_NAMES, clean, features, log_drift
from components.c1_disruption.ml.drift.evaluation import (
    Predictions,
    learning_curve,
    leave_one_student_out,
    rolling_origin,
    score,
)
from components.c1_disruption.ml.drift import settings
from components.c1_disruption.ml.drift.model import DriftModel, choose_k, gate_evidence
from components.c1_disruption.tests.ml import fixtures

FAST = 40  # trees in tests (the real setting is ml/drift/settings.py)


def fast_model() -> DriftModel:
    return DriftModel(n_estimators=FAST)


@pytest.fixture(scope="module")
def data():
    return fixtures.records()


@pytest.fixture(scope="module")
def trained(data):
    return fast_model().fit(data)


# --- data -------------------------------------------------------------------------

def test_every_fixture_record_is_labelled_synthetic(data):
    assert {r["dataset"] for r in data} == {"SYNTHETIC"}


def test_features_and_target():
    rec = {"studentId": "a", "taskType": "Digital", "priority": "High", "estimatedMinutes": 60,
           "actualMinutes": 90, "date": "2026-10-10", "startHour": 19}  # a Saturday
    X = features([rec])
    assert X.shape == (1, len(FEATURE_NAMES))
    row = dict(zip(FEATURE_NAMES, X[0]))
    assert (row["type_Digital"], row["weekday"], row["weekend"], row["start_hour"], row["priority_score"]) == (1, 5, 1, 19, 1)
    assert log_drift([rec])[0] == pytest.approx(np.log(1.5))
    with pytest.raises(ValueError, match="Gaming"):
        features([{**rec, "taskType": "Gaming"}])


def test_exclusion_rule_subtracts_or_drops_disruption_time():
    base = {"studentId": "a", "taskType": "Analog", "priority": "Low", "estimatedMinutes": 60, "date": "2026-10-07",
            "startHour": 9}
    kept = clean([
        {**base, "actualMinutes": 100, "overlapMinutes": 30},   # → 70
        {**base, "actualMinutes": 100, "overlapMinutes": 60},   # > 50% of the span → dropped
        {**base, "actualMinutes": 15, "overlapMinutes": 7},     # 8 min left < 10 → dropped
        {**base, "actualMinutes": None},                        # not done → dropped
        {**base, "actualMinutes": 50},                          # no overlap → unchanged
    ])
    assert [r["actualMinutes"] for r in kept] == [70, 50]


# --- shrinkage ------------------------------------------------------------------------

def test_choose_k_trusts_consistent_students_and_pools_noise():
    rng = np.random.default_rng(0)
    students = [s for s in "abcd" for _ in range(20)]
    consistent = np.array([{"a": 0.5, "b": -0.4, "c": 0.3, "d": -0.2}[s] for s in students]) + rng.normal(0, 0.02, 80)
    assert choose_k(students, consistent) <= 2
    noise = rng.normal(0, 0.3, 80)
    assert choose_k(students, noise) >= 20


def test_planted_student_drift_is_recovered(trained):
    queries = [{"studentId": s, "taskType": "Analog", "priority": "Medium", "estimatedMinutes": 60,
                "date": "2026-10-07", "startHour": 10} for s in ("s1", "s4")]
    high, low = trained.predict(queries)
    assert high.log_point > 0.25  # planted +0.4
    assert low.log_point < -0.05  # planted −0.2
    assert high.n == 60 and 0 < high.weight <= 1


QUERY = {"taskType": "Analog", "priority": "Medium", "estimatedMinutes": 60, "date": "2026-10-07", "startHour": 10}


def test_day_one_student_gets_their_own_estimate_until_the_model_has_earned_trust(trained):
    # Earned-trust gate (16 Oct 2026): no evidence yet → drift 1.0, range widened to contain it.
    new, known = trained.predict([{**QUERY, "studentId": "brand-new"}, {**QUERY, "studentId": "s1"}])
    assert (new.n, new.weight, new.trusted, new.log_point) == (0, 0.0, False, 0.0)
    assert new.log_low <= 0.0 <= new.log_high
    assert known.trusted and known.log_point > 0.25


def test_without_the_gate_a_day_one_student_gets_the_pooled_median(data):
    model = DriftModel(n_estimators=FAST, gate=False).fit(data)
    (new,) = model.predict([{**QUERY, "studentId": "brand-new"}])
    pooled_median = float(model.forest.predict(features([QUERY]), quantiles=0.5)[0])
    assert new.trusted and new.log_point == pytest.approx(pooled_median)


def test_the_point_is_the_median_and_mean_reproduces_the_old_model(data):
    assert settings.POINT_QUANTILE == 0.5
    old = DriftModel(n_estimators=FAST, gate=False, point_quantile="mean").fit(data)
    (p,) = old.predict([{**QUERY, "studentId": "brand-new"}])
    assert p.log_point == pytest.approx(float(old.forest.predict(features([QUERY]), quantiles="mean")[0]))


# --- earned-trust gate ----------------------------------------------------------------------

def test_gate_is_open_for_every_fixture_student_with_planted_drift(trained):
    assert all(t.trusted and t.n_recent == settings.GATE_LOOKBACK for t in trained.trust.values())
    assert all(t.model_mae < t.b0_mae for t in trained.trust.values())


def test_gate_stays_closed_for_a_student_whose_estimates_are_already_right(data):
    exact = [{**r, "studentId": "exact", "actualMinutes": r["estimatedMinutes"]} for r in data if r["studentId"] == "s3"]
    model = DriftModel(n_estimators=FAST).fit(data + exact)
    assert model.trust["exact"].b0_mae == 0 and not model.is_trusted("exact")
    (p,) = model.predict([{**QUERY, "studentId": "exact"}])
    assert (p.trusted, p.log_point) == (False, 0.0)


def test_gate_needs_enough_evidence_and_respects_the_margin():
    records = [{"studentId": "a", "estimatedMinutes": 60, "actualMinutes": 90, "date": f"2026-09-0{d}"} for d in (1, 2, 3)]
    y = np.log(np.full(3, 1.5))
    perfect = y.copy()  # an oracle forest: model error 0, B0 error 30 min
    assert not gate_evidence(records, y, perfect, k=0, min_records=5)["a"].trusted   # 3 < 5 records
    assert gate_evidence(records, y, perfect, k=0, min_records=3)["a"].trusted
    assert not gate_evidence(records, y, perfect, k=0, min_records=3, margin=1.0)["a"].trusted


def test_gate_evidence_uses_only_earlier_days_for_the_shrinkage_term():
    # Forest says 0 (no drift); the student's residuals are +log 2 on day 1 and day 2.
    records = [{"studentId": "a", "estimatedMinutes": 60, "actualMinutes": 120, "date": d}
               for d in ("2026-09-01", "2026-09-02")]
    y, oof = np.log(np.full(2, 2.0)), np.zeros(2)
    t = gate_evidence(records, y, oof, k=0, min_records=1, lookback=2)["a"]
    # Day 1 has no earlier day → model = 60 min (error 60); day 2 uses day 1 → 120 min (error 0).
    assert t.model_mae == pytest.approx(30) and t.b0_mae == pytest.approx(60) and t.trusted


def test_switching_the_gate_off_restores_ungated_predictions(data):
    gated, ungated = DriftModel(n_estimators=FAST).fit(data), DriftModel(n_estimators=FAST, gate=False).fit(data)
    queries = [{**QUERY, "studentId": s} for s in ("s1", "s4", "brand-new")]
    g, u = gated.predict(queries), ungated.predict(queries)
    assert [p.log_point for p in g[:2]] == pytest.approx([p.log_point for p in u[:2]])  # trusted students: same
    assert g[2].log_point == 0.0 and u[2].log_point != 0.0


def test_range_contains_the_point_and_converts_to_minutes(trained):
    (p,) = trained.predict([{"studentId": "s3", "taskType": "Digital", "priority": "High", "estimatedMinutes": 120,
                             "date": "2026-10-07", "startHour": 14}])
    point, low, high = p.corrected_minutes(120)
    assert low < high and p.log_low < p.log_high
    assert point == pytest.approx(120 * np.exp(p.log_point))


# --- evaluation ----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def warm(data):
    return {
        name: rolling_origin(data, factory, min_history_days=2, step_days=6)
        for name, factory in {
            "model": fast_model,
            **{cls.name: cls for cls in baselines.BASELINES},
        }.items()
    }


def test_model_beats_b0_and_b1_warm(warm):
    mae = {name: score(p)["maeMinutes"] for name, p in warm.items()}
    assert mae["model"] < mae["B0 drift = 1.0"]
    assert mae["model"] < mae["B1 global mean"]
    assert all(v is not None for v in mae.values())


def test_interval_coverage_is_near_nominal(warm):
    coverage = score(warm["model"])["coverage"]
    assert 0.6 <= coverage <= 0.97  # nominal 80% (q10–q90)
    assert score(warm["B2 per-student mean"])["coverage"] is None  # baselines give no range


def test_learning_curve_bins(warm):
    rows = learning_curve(warm["model"])
    assert [r["nFrom"] for r in rows] == [0, 1, 5, 10, 20, 40]
    assert sum(r["n"] for r in rows) == score(warm["model"])["n"]


def test_cold_start_runs_for_model_and_baselines(data):
    for factory in (fast_model, *baselines.BASELINES):
        result = score(leave_one_student_out(data, factory))
        assert result["n"] == len(data)


def test_leave_one_student_out_never_sees_the_held_out_student(data):
    seen = []

    class Spy(baselines.B1GlobalMean):
        def fit(self, records):
            seen.append({r["studentId"] for r in records})
            return super().fit(records)

    p = leave_one_student_out(data, Spy)
    students = sorted({r["studentId"] for r in data})
    assert [s not in train for s, train in zip(students, seen)] == [True] * len(students)
    assert set(p.n_seen) == {0}


def test_rolling_origin_trains_only_on_the_past(data):
    calls = []

    class Spy(baselines.B2StudentMean):
        def fit(self, records):
            self._train = records
            return super().fit(records)

        def predict_log(self, records):
            calls.append((self._train, records))
            return super().predict_log(records)

    rolling_origin(data, Spy, min_history_days=2, step_days=6)
    for train, test in calls:
        student = test[0]["studentId"]
        first_test_day = min(r["date"] for r in test)
        assert all(r["date"] < first_test_day for r in train if r["studentId"] == student)


def test_future_data_does_not_change_past_predictions(data):
    def preds(records):
        p = rolling_origin(records, baselines.B3ShrinkageOnly, min_history_days=2, step_days=6)
        return {(r["studentId"], r["date"], i): v for i, (r, v) in enumerate(zip(p.records, p.log_pred))
                if r["studentId"] == "s1" and r["date"] < "2026-09-15"}

    corrupted = copy.deepcopy(data)
    for r in corrupted:
        if r["studentId"] == "s1" and r["date"] >= "2026-09-15":
            r["actualMinutes"] = r["estimatedMinutes"] * 10
    assert preds(corrupted) == preds(data)


def test_null_persona_model_does_not_invent_drift():
    null = fixtures.records(offsets={f"n{i}": 0.0 for i in range(5)}, digital_effect=0.0)
    model = fast_model().fit(null)
    queries = [{"studentId": "n0", "taskType": t, "priority": "High", "estimatedMinutes": 60, "date": "2026-10-07",
                "startHour": 10} for t in ("Digital", "Analog", "Meeting")]
    assert max(abs(p.log_point) for p in model.predict(queries)) < 0.1


def test_score_of_nothing():
    assert score(Predictions()) == {"maeMinutes": None, "maeLog": None, "coverage": None, "n": 0, "trustedShare": None}


def test_score_reports_how_often_the_gate_let_the_model_correct(warm, data):
    assert 0 <= score(warm["model"])["trustedShare"] <= 1
    assert score(warm["B0 drift = 1.0"])["trustedShare"] is None  # baselines have no gate
    cold = score(leave_one_student_out(data, fast_model))
    assert cold["trustedShare"] == 0.0  # an unseen student never passes the gate


# --- fallback ---------------------------------------------------------------------------------

TASK = {"type": "Digital", "priority": "High", "estimatedHours": 2, "plannedStart": "14:00"}
CTX = {"date": "2026-10-07", "planFrom": "09:00"}


@pytest.mark.parametrize("model", [None, DriftModel()], ids=["no model", "untrained"])
def test_no_or_untrained_model_falls_back_to_drift_1(model):
    corrector = ModelCorrector(model)
    assert corrector.model_on is False
    c = corrector.correct("s1", TASK, CTX)
    assert (c.point_hours, c.low_hours, c.high_hours, c.source) == (2, 2, 2, "fallback")


def test_a_failing_model_falls_back_and_planning_continues(trained, monkeypatch):
    corrector = ModelCorrector(trained)
    monkeypatch.setattr(trained, "predict", lambda records: (_ for _ in ()).throw(RuntimeError("boom")))
    assert corrector.correct("s1", TASK, CTX).source == "fallback"


def test_a_closed_gate_gives_the_estimate_with_source_gate(trained):
    c = ModelCorrector(trained).correct("brand-new", TASK, CTX)
    assert (c.point_hours, c.source) == (2, "gate")
    assert c.low_hours <= 2 <= c.high_hours


def test_a_trained_model_corrects_with_an_ordered_range(trained):
    c = ModelCorrector(trained).correct("s1", TASK, CTX)
    assert c.source == "model"
    assert c.low_hours <= c.point_hours <= c.high_hours
    assert c.point_hours > 2  # s1 runs over (planted +0.4, Digital +0.2)


def test_model_1_plugged_into_the_api(trained):
    from components.c1_disruption.tests.api.client import setup

    ctx = setup("2026-10-07T09:00", corrector=ModelCorrector(trained))
    ctx.call("PUT", "/api/me/settings", body={"workStart": "09:00", "workEnd": "18:00"})
    task = ctx.call("POST", "/api/tasks", body={"title": "Lab", "type": "Digital", "priority": "High", "estimatedHours": 1,
                                                 "deadline": "2026-10-07T23:59", "plannedDate": "2026-10-07"}).json()
    report = ctx.call("POST", "/api/disruptions", body={"date": "2026-10-07", "type": "transport_delay", "start": "09:00",
                                                         "timeLostMinutes": 60, "severity": 1, "confirmed": True}).json()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    assert mvd["modelOn"] is True
    (log,) = mvd["taskLog"]
    # "u1" has no history: the gate keeps their own estimate.
    assert log["taskId"] == task["id"] and log["correctionSource"] == "gate" and log["correctedHours"] == 1
    assert log["correctedLowHours"] <= log["correctedHours"] <= log["correctedHighHours"]


def test_model_1_in_the_api_corrects_a_student_who_earned_trust(trained):
    from components.c1_disruption.tests.api.client import setup

    ctx = setup("2026-10-07T09:00", corrector=ModelCorrector(trained))
    call = lambda method, path, body=None: ctx.call(method, path, user="s1", body=body)  # "s1" has fixture history
    call("PUT", "/api/me/settings", {"workStart": "09:00", "workEnd": "18:00"})
    call("POST", "/api/tasks", {"title": "Lab", "type": "Digital", "priority": "High", "estimatedHours": 1,
                                "deadline": "2026-10-07T23:59", "plannedDate": "2026-10-07"})
    report = call("POST", "/api/disruptions", {"date": "2026-10-07", "type": "transport_delay", "start": "09:00",
                                               "timeLostMinutes": 60, "severity": 1, "confirmed": True}).json()
    (log,) = call("POST", f"/api/disruptions/{report['id']}/mvd").json()["taskLog"]
    assert log["correctionSource"] == "model" and log["correctedHours"] > 1  # s1 runs over


def test_gate_students_counts_open_and_closed_at_the_last_point():
    from components.c1_disruption.ml.drift.evaluation import gate_students

    p = Predictions(records=[{"studentId": s} for s in ("a", "a", "b", "c")], log_pred=[0] * 4, log_low=[0] * 4,
                    log_high=[0] * 4, n_seen=[3, 9, 5, 0], trusted=[False, True, True, False])
    assert gate_students(p) == {"students": 3, "open": 2, "closed": 1, "everOpen": 2}
    assert gate_students(Predictions(records=[{"studentId": "a"}], log_pred=[0], log_low=[None], log_high=[None],
                                     n_seen=[0], trusted=[None])) is None  # baselines have no gate


def test_keep_before_wraps_old_results_once():
    from components.c1_disruption.ml.drift.evaluation import keep_before

    before = keep_before("# Old title\n\n## Variant: planted\n\n| a |", "## Before gate (old run)")
    assert before == "## Before gate (old run)\n\n\n### Variant: planted\n\n| a |\n"
    assert keep_before("# New\n\n## Variant\n\n" + before, "## Before gate (other)") == before
    assert keep_before(None, "## Before gate") is None
