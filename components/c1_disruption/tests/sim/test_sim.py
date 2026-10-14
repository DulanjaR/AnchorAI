"""Simulation pipeline (everything SYNTHETIC): loader, layers B–D, experiment."""
from pathlib import Path

import pytest

from components.c1_disruption.ml.drift.data import clean
from components.c1_disruption.sim import events as events_module
from components.c1_disruption.sim.events import build_events, event_metrics
from components.c1_disruption.sim.experiment import run_world, to_markdown
from components.c1_disruption.sim.generate import generate
from components.c1_disruption.sim.personas import FormatError, Persona, PlannedTask, load_personas, load_tasks

EXAMPLES = Path(__file__).parents[2] / "sim" / "examples"


def three_weeks() -> tuple[dict[str, Persona], list[PlannedTask]]:
    """Two SYNTHETIC personas × 21 days × 4 Digital/Analog tasks (no None-EF types)."""
    personas = {
        "A": Persona("A", "SYNTHETIC over-runner", "08:00", "20:00",
                     ({"id": "b1", "label": "Lunch", "start": "12:30", "end": "13:30"},),
                     drift={"Digital": 1.5, "Analog": 1.2, "Meeting": 1.0, "Fixed": 1.0}, noise_sd=0.08,
                     preferred_strategy="no_compress"),
        "B": Persona("B", "SYNTHETIC accurate", "09:00", "18:00", drift={"Digital": 1.0, "Analog": 1.0, "Meeting": 1.0,
                                                                          "Fixed": 1.0}, noise_sd=0.05),
    }
    tasks = []
    for pid in personas:
        for day in range(1, 22):
            for i, (kind, minutes, start) in enumerate((("Digital", 120, "09:00"), ("Analog", 90, "11:00"),
                                                        ("Digital", 60, "14:00"), ("Analog", 60, "16:00"))):
                end = f"{int(start[:2]) + (int(start[3:]) + minutes) // 60:02d}:{(int(start[3:]) + minutes) % 60:02d}"
                tasks.append(PlannedTask(pid, day, f"{pid}{day}-{i}", f"Task {i}", kind, ("High", "Medium")[i % 2],
                                         minutes, i % 2, planned_start=start, planned_end=end))
    return personas, tasks


# --- layer A: loader -----------------------------------------------------------------------

def test_examples_load():
    personas = load_personas(EXAMPLES / "personas.csv")
    tasks = load_tasks(EXAMPLES / "tasks.csv", personas)
    assert list(personas) == ["X01", "X02"] and len(tasks) == 10
    x01 = personas["X01"]
    assert x01.protected_blocks[1] == {"id": "b2", "label": "Sleep", "start": "22:00", "end": "06:00"}
    assert (x01.drift["Digital"], x01.evening_factor, x01.preferred_strategy) == (1.4, 1.2, "no_compress")
    t2 = next(t for t in tasks if t.task_id == "t2")
    assert (t2.date, t2.deadline) == ("2026-09-07", "2026-09-08T23:59")


@pytest.mark.parametrize(
    ("file", "row", "message"),
    [
        ("tasks", "X01,1,t9,Play,Gaming,High,60,0,,,,", "line 2, column 'type'"),
        ("tasks", "Z99,1,t9,Read,Analog,High,60,0,,,,", "line 2, column 'personaId'"),
        ("tasks", "X01,1,t9,Read,Analog,High,60,0,,10:00,,", "line 2, column 'plannedEnd'"),
        ("tasks", "X01,0,t9,Read,Analog,High,60,0,,,,", "line 2, column 'day'"),
        ("personas", "P01,Late riser,10:00,09:00,,,,,,,,,", "line 2, column 'workEnd'"),
        ("personas", "P01,Napper,09:00,18:00,Nap 1400-1430,,,,,,,,", "line 2, column 'protectedBlocks'"),
        ("personas", "P01,Picky,09:00,18:00,,,,,,,,,squeeze_all", "line 2, column 'preferredStrategy'"),
    ],
)
def test_loader_names_file_line_and_column(tmp_path, file, row, message):
    header = {
        "tasks": (EXAMPLES / "tasks.csv").read_text(encoding="utf-8").splitlines()[0],
        "personas": (EXAMPLES / "personas.csv").read_text(encoding="utf-8").splitlines()[0],
    }[file]
    path = tmp_path / f"{file}.csv"
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    with pytest.raises(FormatError, match=message):
        if file == "tasks":
            load_tasks(path, load_personas(EXAMPLES / "personas.csv"))
        else:
            load_personas(path)


# --- layers B and C -----------------------------------------------------------------------------

def test_same_seed_same_world_and_every_record_is_synthetic():
    personas, tasks = three_weeks()
    a, b = generate(personas, tasks, 11), generate(personas, tasks, 11)
    assert a.records == b.records and a.disruptions == b.disruptions
    assert {r["dataset"] for r in a.records} == {"SYNTHETIC"}
    assert generate(personas, tasks, 12).records != a.records


def test_variants_share_disruptions_and_noise():
    personas, tasks = three_weeks()
    worlds = {v: generate(personas, tasks, 11, v) for v in ("planted", "null", "misspecified")}
    assert worlds["planted"].disruptions == worlds["null"].disruptions == worlds["misspecified"].disruptions
    # B's planted drift is 1.0, so planted and null give B the same actual minutes.
    b_planted = {k: v for k, v in worlds["planted"].actual_minutes.items() if k[0] == "B"}
    b_null = {k: v for k, v in worlds["null"].actual_minutes.items() if k[0] == "B"}
    assert b_planted == b_null
    assert worlds["misspecified"].actual_minutes != worlds["planted"].actual_minutes


def test_null_persona_has_no_drift():
    personas, tasks = three_weeks()
    world = generate(personas, tasks, 11, "null")
    ratios = [world.actual_minutes[(t.persona_id, t.task_id)] / t.estimated_minutes for t in tasks]
    assert 0.95 < sum(ratios) / len(ratios) < 1.05


def test_disruption_overlap_is_recorded_and_removed_by_the_exclusion_rule():
    personas, tasks = three_weeks()
    world = generate(personas, tasks, 11)
    overlapped = [r for r in world.records if r["overlapMinutes"] > 0]
    assert overlapped, "seed 11 should put some disruptions over planned tasks"
    cleaned = {(r["studentId"], r["taskId"]): r for r in clean(world.records)}
    for r in overlapped:
        kept = cleaned.get((r["studentId"], r["taskId"]))
        if kept is not None:
            true = world.actual_minutes[(r["studentId"], r["taskId"])]
            assert kept["actualMinutes"] == pytest.approx(true, abs=0.1)


# --- layer D ------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def world_and_events():
    personas, tasks = three_weeks()
    world = generate(personas, tasks, 11)
    events, skipped = build_events(world, n_estimators=20)
    return world, events, skipped


def test_events_compare_raw_and_corrected_with_ptvr_zero(world_and_events):
    world, events, skipped = world_and_events
    # Digital / Analog only: every disruption that overlaps a task can be planned.
    assert {s.kind for s in skipped} <= {"no_effect"}
    compared = [e for e in events if e.corrected is not None]
    assert compared and all(e.date >= "2026-09-14" for e in compared)  # week 1 has no training data
    for e in compared:
        row = event_metrics(world, e)
        assert row["raw"]["ptvr"] == 0 and row["corrected"]["ptvr"] == 0
        assert 0 <= row["decisionChangeRate"] <= 1
        assert row["dataset"] == "SYNTHETIC"


def test_corrected_plans_use_longer_durations_for_the_over_runner(world_and_events):
    _, events, _ = world_and_events
    e = next(e for e in events if e.persona_id == "A" and e.corrected is not None)
    raw = {t["id"]: t["estimatedHours"] for t in e.raw["tasks"]}
    corrected = {t["id"]: t["estimatedHours"] for t in e.corrected["tasks"]}
    assert all(corrected[k] > raw[k] for k in raw)


def test_the_model_for_an_event_only_sees_earlier_weeks(monkeypatch):
    personas, tasks = three_weeks()
    world = generate(personas, tasks, 11)
    last_training_day = []  # one entry per model fit, in fit order
    original = events_module.DriftModel.fit

    def spy(self, records):
        last_training_day.append(max(r["date"] for r in records))
        return original(self, records)

    monkeypatch.setattr(events_module.DriftModel, "fit", spy)
    events, _ = build_events(world, n_estimators=10)
    # Models are fitted once per week, in time order, for the weeks that have events.
    weeks = sorted({events_module._week_start(e.date) for e in events if e.corrected is not None})
    assert len(weeks) == len(last_training_day) >= 2
    for week_start, last in zip(weeks, last_training_day):
        assert last < week_start  # no record from the event's own week or later


def test_unplannable_events_are_skipped_and_counted():
    personas, tasks = three_weeks()
    tasks = [PlannedTask(t.persona_id, t.day, t.task_id, t.title, "Meeting" if t.task_id.endswith("-0") else t.type,
                         t.priority, t.estimated_minutes, t.deadline_in_days, t.deadline_time, t.planned_start,
                         t.planned_end) for t in tasks]
    world = generate(personas, tasks, 11)
    events, skipped = build_events(world, n_estimators=10)
    environment = [key for key, d in world.disruptions.items()
                   if d.type in ("power_outage", "transport_delay") and events_module.overlaps_a_task(world, *key)]
    cannot_plan = [s for s in skipped if s.kind == "cannot_plan"]
    assert len(cannot_plan) == len(environment) > 0  # every effective environment event hits the Meeting's None EF
    assert all("Meeting" in s.reason for s in cannot_plan)


def test_run_world_and_report_are_labelled_synthetic():
    personas, tasks = three_weeks()
    result = run_world(generate(personas, tasks, 11), n_estimators=10)
    assert result["dataset"] == "SYNTHETIC"
    assert set(result["model1"]["warm"]) == {"model", "B0 drift = 1.0", "B1 global mean", "B2 per-student mean",
                                             "B3 shrinkage only"}
    assert set(result["model2"]) == {"fixed order", "most accepted", "random", "bandit"}
    report = {"label": "SYNTHETIC — pipeline validation only, not a research finding", "personas": 2,
              "tasks": len(tasks), "runs": [result]}
    text = to_markdown(report)
    assert text.startswith("# C1 simulation results — SYNTHETIC")
    assert "## Variant: planted (SYNTHETIC)" in text
