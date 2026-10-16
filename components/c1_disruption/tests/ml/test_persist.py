"""Saving / loading ML Model 1 and plugging the file into the API (SYNTHETIC fixture)."""
import json

import joblib
import pytest

from components.c1_disruption.app import main
from components.c1_disruption.app.services.planning import NoDrift
from components.c1_disruption.ml.drift.corrector import ModelCorrector, load_corrector
from components.c1_disruption.ml.drift.model import DriftModel
from components.c1_disruption.ml.drift.persist import FORMAT_VERSION, load_model, metadata_path, save_model
from components.c1_disruption.tests.api.client import setup
from components.c1_disruption.tests.ml import fixtures

QUERIES = [
    {"studentId": s, "taskType": t, "priority": "High", "estimatedMinutes": 90, "date": "2026-10-07", "startHour": h}
    for s in ("s1", "s4", "new-student") for t, h in (("Digital", 19), ("Analog", 9))
]


@pytest.fixture(scope="module")
def saved(tmp_path_factory):
    model = DriftModel(n_estimators=30).fit(fixtures.records())
    path = tmp_path_factory.mktemp("model") / "c1_drift_model.joblib"
    meta = save_model(model, path, dataset="SYNTHETIC")
    return model, path, meta


def test_round_trip_gives_identical_predictions(saved):
    model, path, _ = saved
    loaded, _ = load_model(path)
    assert loaded.predict(QUERIES) == model.predict(QUERIES)
    assert loaded.k == model.k and loaded.offsets == model.offsets
    assert loaded.trust == model.trust  # earned-trust gate evidence is saved with the model


def test_metadata_records_the_median_point_and_the_gate(saved):
    _, _, meta = saved
    assert FORMAT_VERSION == 2  # files from before the gate (format 1) are refused → drift 1.0
    assert meta["pointQuantile"] == 0.5
    assert meta["gate"] == {"enabled": True, "lookback": 20, "minRecords": 5, "margin": 0.05}
    assert meta["trustedStudents"] == 6


def test_metadata_file(saved):
    model, path, meta = saved
    on_disk = json.loads(metadata_path(path).read_text(encoding="utf-8"))
    assert on_disk == meta
    assert metadata_path(path).name == "c1_drift_model.joblib.json"
    assert (meta["format"], meta["records"], meta["students"]) == (FORMAT_VERSION, 360, 6)
    assert (meta["dataset"], meta["synthetic"], meta["k"]) == ("SYNTHETIC", True, model.k)
    assert set(meta["libraries"]) == {"numpy", "scikit-learn", "quantile-forest"}
    assert meta["trainedAt"].endswith("+00:00")


def test_load_reports_whether_library_versions_match(saved):
    _, path, _ = saved
    _, meta = load_model(path)
    assert meta["librariesMatch"] is True


def test_an_untrained_model_cannot_be_saved(tmp_path):
    with pytest.raises(ValueError, match="trained"):
        save_model(DriftModel(), tmp_path / "x.joblib", dataset="SYNTHETIC")


@pytest.mark.parametrize("path", ["", None])
def test_no_setting_means_no_drift(path):
    assert isinstance(load_corrector(path), NoDrift)


def test_missing_file_means_no_drift(tmp_path):
    assert isinstance(load_corrector(tmp_path / "nope.joblib"), NoDrift)


def test_missing_metadata_means_no_drift(saved, tmp_path):
    model, _, _ = saved
    lone = tmp_path / "lone.joblib"
    joblib.dump(model, lone)  # no .json next to it
    assert isinstance(load_corrector(lone), NoDrift)


def test_a_file_that_is_not_a_drift_model_means_no_drift(tmp_path):
    path = tmp_path / "other.joblib"
    joblib.dump({"not": "a model"}, path)
    metadata_path(path).write_text(json.dumps({"format": FORMAT_VERSION}), encoding="utf-8")
    assert isinstance(load_corrector(path), NoDrift)


def test_an_unknown_format_means_no_drift(saved, tmp_path):
    model, _, _ = saved
    path = tmp_path / "future.joblib"
    save_model(model, path, dataset="SYNTHETIC")
    metadata_path(path).write_text(json.dumps({"format": 99}), encoding="utf-8")
    assert isinstance(load_corrector(path), NoDrift)


def test_a_saved_model_loads_as_a_model_corrector(saved):
    _, path, _ = saved
    corrector = load_corrector(path)
    assert isinstance(corrector, ModelCorrector) and corrector.model_on
    assert corrector.meta["dataset"] == "SYNTHETIC"


def _mvd_for(user_id: str):
    ctx = setup("2026-10-07T09:00")
    ctx.call("PUT", "/api/me/settings", user=user_id, body={"workStart": "08:00", "workEnd": "20:00"})
    for title, kind, hours in (("Lab code", "Digital", 1.5), ("Reading", "Analog", 1)):
        ctx.call("POST", "/api/tasks", user=user_id, body={"title": title, "type": kind, "priority": "High",
                                                            "estimatedHours": hours, "deadline": "2026-10-08T23:59",
                                                            "plannedDate": "2026-10-07"})
    report = ctx.call("POST", "/api/disruptions", user=user_id, body={
        "date": "2026-10-07", "type": "transport_delay", "start": "09:00", "timeLostMinutes": 60, "severity": 2,
        "confirmed": True}).json()
    return ctx.call("POST", f"/api/disruptions/{report['id']}/mvd", user=user_id).json()


def test_api_uses_the_model_file_from_the_setting(saved, monkeypatch):
    _, path, _ = saved
    monkeypatch.setattr(main.c1_settings, "drift_model_path", str(path))
    mvd = _mvd_for("s1")  # s1 over-runs in the fixture (+0.4 log drift, Digital +0.2)
    assert mvd["modelOn"] is True
    for log in mvd["taskLog"]:
        assert log["correctionSource"] == "model"
        assert log["correctedHours"] > log["estimatedHours"]
        assert log["correctedLowHours"] <= log["correctedHours"] <= log["correctedHighHours"]
    planned = {t["id"]: t["estimatedHours"] for t in mvd["plan"]["tasks"]}
    assert planned == {log["taskId"]: log["correctedHours"] for log in mvd["taskLog"]}  # the engine planned with them


def test_api_with_a_missing_model_file_plans_with_drift_1(tmp_path, monkeypatch):
    monkeypatch.setattr(main.c1_settings, "drift_model_path", str(tmp_path / "missing.joblib"))
    mvd = _mvd_for("s1")
    assert mvd["modelOn"] is False
    assert all(log["correctedHours"] == log["estimatedHours"] for log in mvd["taskLog"])
