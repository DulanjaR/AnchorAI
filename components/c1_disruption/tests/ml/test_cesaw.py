"""CESAW adapter and evaluation (ml/drift/external/cesaw.py).

The real CESAW data is never in the repo (licence not stated). These tests use a tiny
file written in the CESAW column layout; the values are made up and only check the mapping."""
import csv
import random

import pytest

from components.c1_disruption.app.settings import C1Settings
from components.c1_disruption.ml.drift.external import cesaw, settings

COLUMNS = ["project_key", "person_key", "team_key", "wbs_element_key", "plan_item_key", "task_actual_start_date",
           "task_actual_complete_date", "task_actual_time_minutes", "task_plan_time_minutes", "phase_key",
           "phase_short_name", "process_name"]


def row(person, start, actual, plan, phase="Code"):
    return [100, person, 1, 1, 1, start, start, actual, plan, 1, phase, "P"]


def write(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(COLUMNS)
        writer.writerows(rows)


def test_mapping_and_dropped_counts(tmp_path):
    write(tmp_path / settings.TASK_FILE, [
        row(7, "10/29/2012 13:12", 120, 90, "Code Inspect"),   # kept: Monday 13:00 hour
        row(7, "2/3/2013 6:05", 30, 60),                        # kept: single-digit month/hour
        row(7, "11/1/2012 9:00", 20, 0),                        # plan <= 0
        row(8, "11/1/2012 9:00", 0, 30),                        # actual <= 0
        row(8, "\\N", 10, 30),                                  # missing start
        row(8, "0016-01-11 16:22:26", 10, 30),                  # malformed start
        row(8, "11/2/2012 10:30", 45, 30),
    ])
    records, report = cesaw.load_cesaw(tmp_path)  # a folder works
    assert report == {"rows": 7, "droppedPlanNotPositive": 1, "droppedActualNotPositive": 1,
                      "droppedNoStartTime": 2, "kept": 3, "developers": 2}
    first = records[0]
    assert (first["studentId"], first["taskType"], first["priority"]) == ("D7", "Digital", "Medium")
    assert (first["estimatedMinutes"], first["actualMinutes"]) == (90, 120)
    assert (first["date"], first["startHour"], first["phase"]) == ("2012-10-29", 13, "Code Inspect")
    assert records[1]["date"] == "2013-02-03" and records[1]["startHour"] == 6


def test_a_file_path_also_works_and_a_missing_one_is_a_clear_error(tmp_path):
    write(tmp_path / "x.csv", [row(1, "1/2/2013 8:00", 5, 5)])
    assert cesaw.load_cesaw(tmp_path / "x.csv")[1]["kept"] == 1
    with pytest.raises(FileNotFoundError, match="C1_CESAW_PATH"):
        cesaw.load_cesaw(tmp_path / "nothing")


def test_the_path_is_a_c1_setting(monkeypatch):
    monkeypatch.setenv("C1_CESAW_PATH", "D:/somewhere/CESAW")
    assert C1Settings().cesaw_path == "D:/somewhere/CESAW"
    assert C1Settings(_env_file=None, cesaw_path="").cesaw_path == ""


def small_world(tmp_path):
    rng = random.Random(3)
    rows = []
    for person in (1, 2, 3, 4):
        for day in range(1, 26):
            for _ in range(2):
                plan = rng.choice([30, 60, 90])
                rows.append(row(person, f"3/{day}/2013 {rng.randint(8, 17)}:00", plan * (1.5 if person == 1 else 1), plan))
    write(tmp_path / settings.TASK_FILE, rows)
    return cesaw.load_cesaw(tmp_path)


def test_warm_sample_is_seeded_and_needs_enough_days(tmp_path):
    records, _ = small_world(tmp_path)
    assert cesaw.warm_developers(records) == cesaw.warm_developers(records) == ["D1", "D2", "D3", "D4"]
    assert cesaw.warm_developers(records[:30]) == []


def test_cold_groups_cover_every_developer_once_and_are_seeded():
    developers = [f"D{i}" for i in range(23)]
    groups = cesaw.cold_groups(developers)
    assert len(groups) == settings.COLD_FOLDS
    assert sorted(d for g in groups for d in g) == sorted(developers)
    assert {len(g) for g in groups} == {2, 3}
    assert cesaw.cold_groups(developers) == groups
    assert len(cesaw.cold_groups(developers[:3])) == 3  # never an empty group


def test_evaluation_runs_on_a_small_file_and_is_labelled_real(tmp_path):
    records, dropped = small_world(tmp_path)
    report = cesaw.evaluate(records, n_estimators=10, n_jobs=1, folds=2)
    assert report["label"] == "REAL (CESAW, professional developers)"
    assert set(report["cold"]) == set(report["warm"]) == {"model", "B0 drift = 1.0", "B1 global mean",
                                                          "B2 per-student mean", "B3 shrinkage only"}
    assert report["cold"]["model"]["n"] == len(records)  # every developer is held out once
    assert report["coldFolds"] == 2
    assert report["cold"]["model"]["coverage"] is not None
    assert report["warm"]["B0 drift = 1.0"]["coverage"] is None
    text = cesaw.to_markdown(report, dropped, cesaw.describe(records))
    assert "REAL (CESAW, professional developers)" in text and "SYNTHETIC" not in text
    assert "not students" in text


# --- earned-trust gate in the CESAW report (16 Oct 2026) -------------------------------------

OLD_RESULTS = """# Model 1 on CESAW — REAL (CESAW, professional developers)

intro

## Cold start — developers held out in groups (n = 0)

| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n |
|---|---|---|---|---|
| model | 80.20 | 0.792 | 0.738 | 60284 |
| B0 drift = 1.0 | 75.04 | 0.760 | – | 60284 |

## Warm — rolling-origin (sampled developers)

| Method | MAE minutes | MAE log ratio | q10–q90 coverage | n |
|---|---|---|---|---|
| model | 82.00 | 0.790 | 0.728 | 13322 |
"""


def test_earlier_results_become_the_before_gate_section_once():
    before = cesaw.before_section(OLD_RESULTS)
    assert before.startswith("## Before gate (run of 15 Oct 2026: mean point, no gate)")
    assert "### Cold start" in before and "# Model 1" not in before
    assert cesaw.before_section(before + "\nmore") .startswith("## Before gate")
    assert cesaw.before_section(f"# new\n\n## Summary\n\n{before}") == before  # kept as it is on the next run
    tables = cesaw.parse_tables(before)
    assert tables["cold"]["model"] == {"maeMinutes": 80.2, "maeLog": 0.792, "coverage": 0.738}
    assert tables["cold"]["B0 drift = 1.0"]["coverage"] is None and tables["warm"]["model"]["maeMinutes"] == 82.0


def test_report_shows_the_gate_and_keeps_the_before_results(tmp_path):
    records, dropped = small_world(tmp_path)
    report = cesaw.evaluate(records, n_estimators=10, n_jobs=1, folds=2)
    assert report["gate"]["cold"]["openShare"] == 0.0  # an unseen developer never passes the gate
    warm = report["gate"]["warm"]
    assert warm["developers"] == 4 and warm["developersEverOpen"] + warm["developersNeverOpen"] == 4
    assert warm["whereOpen"]["model"]["n"] == warm["open"] == warm["whereOpen"]["B0"]["n"]
    text = cesaw.to_markdown(report, dropped, cesaw.describe(records), cesaw.before_section(OLD_RESULTS))
    assert "## Summary: does the gate close the gap to B0?" in text
    assert "| Cold start MAE minutes | 80.20 |" in text  # the before-gate number, next to the new one
    assert "## Before gate" in text and "SYNTHETIC" not in text
    assert ("fell back to B0 for most predictions" in text) == ((warm["openShare"] or 0) < 0.5)
