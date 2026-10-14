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
from components.c1_disruption.ml.drift.model import DriftModel, choose_k
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


def test_day_one_student_gets_the_pooled_estimate(trained):
    query = {"taskType": "Analog", "priority": "Medium", "estimatedMinutes": 60, "date": "2026-10-07", "startHour": 10}
    new, known = trained.predict([{**query, "studentId": "brand-new"}, {**query, "studentId": "s1"}])
    pooled = float(trained.forest.predict(features([query]), quantiles="mean")[0])
    assert (new.n, new.weight) == (0, 0.0)
    assert new.log_point == pytest.approx(pooled)
    assert known.log_point != pytest.approx(pooled)


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
    assert score(Predictions()) == {"maeMinutes": None, "maeLog": None, "coverage": None, "n": 0}


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
    ctx.store.set("users", "s1", ctx.store.get("users", "u1"))  # "s1" has history in the fixture
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd").json()
    assert mvd["modelOn"] is True
    (log,) = mvd["taskLog"]
    assert log["taskId"] == task["id"] and log["correctionSource"] == "model"
    assert log["correctedLowHours"] <= log["correctedHours"] <= log["correctedHighHours"]
