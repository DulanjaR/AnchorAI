"""The owner's SYNTHETIC persona files (sim/data/): loading, schedule frames, special
habits and layer C. Pipeline checks only, not research data."""
import dataclasses
import math
import re
from pathlib import Path

import pytest

from components.c1_disruption.engine.time import to_minutes
from components.c1_disruption.sim.events import build_events, engine_input, event_metrics
from components.c1_disruption.sim.generate import LONG_TASK_TYPES, first_after_night_shift, generate, planted_log_drift
from components.c1_disruption.sim.personas import (
    FormatError,
    day_frame,
    free_minutes,
    load_habits,
    load_personas,
    load_schedule,
    load_tasks,
    night_shift_days,
)

DATA = Path(__file__).parents[2] / "sim" / "data"
PERSONAS, HABITS = DATA / "SYNTHETIC_personas.csv", DATA / "SYNTHETIC_habits.csv"
TASKS, SCHEDULE = DATA / "SYNTHETIC_tasks_planned.csv", DATA / "SYNTHETIC_schedule.csv"


@pytest.fixture(scope="module")
def data():
    personas = load_personas(PERSONAS, HABITS)
    return personas, load_tasks(TASKS, personas), load_schedule(SCHEDULE, personas)


def _slot(task):
    return range(to_minutes(task.planned_start), to_minutes(task.planned_end))


# --- loading ------------------------------------------------------------------------------------

def test_all_files_load(data):
    personas, tasks, schedule = data
    assert sorted(personas) == [f"P{i:02d}" for i in range(1, 11)]
    assert len(tasks) == 589
    assert len(schedule) == 300  # 10 personas × 30 days
    assert {t.day for t in tasks} <= set(range(1, 31))
    assert all(p.label.startswith("SYNTHETIC") for p in personas.values())


def test_habits_file_transcribes_the_special_habits_text():
    import csv

    text = {r["personaId"]: r["specialHabits"] for r in csv.DictReader(open(PERSONAS, encoding="utf-8-sig", newline=""))}
    habits = {r["personaId"]: r for r in csv.DictReader(open(HABITS, encoding="utf-8-sig", newline=""))}
    assert set(habits) == {pid for pid, t in text.items() if t.strip()}
    for pid, row in habits.items():
        numbers = set(re.findall(r"\d+(?:[.:]\d+)?", text[pid]))
        for value in (v for k, v in row.items() if k != "personaId" and v):
            for found in re.findall(r"\d+(?:[.:]\d+)?", value):
                assert found in numbers, (pid, found, text[pid])


def test_habit_fields(data):
    personas, _, _ = data
    assert (personas["P01"].late_factor, personas["P01"].late_from) == (1.10, "21:30")
    assert personas["P07"].after_night_shift_factor == 1.35
    assert personas["P08"].title_drift == (("Module B assignment: section", 1.6), ("Lit review: write synthesis", 1.6))
    assert (personas["P09"].long_task_factor, personas["P09"].long_task_minutes) == (1.30, 180)
    plain = [p for pid, p in personas.items() if pid not in ("P01", "P07", "P08", "P09")]
    assert all(p.late_factor == 1 and p.after_night_shift_factor == 1 and not p.title_drift and p.long_task_minutes is None
               for p in plain)


# --- schedule → engine frame ------------------------------------------------------------------------

def test_every_task_sits_in_a_study_window_and_clashes_with_no_fixed_block(data):
    _, tasks, schedule = data
    for t in tasks:
        free = free_minutes(schedule[(t.persona_id, t.day)])
        assert all(free[m] for m in _slot(t)), (t.persona_id, t.day, t.task_id)


def test_every_task_fits_its_day_frame_without_touching_a_protected_block(data):
    _, tasks, schedule = data
    for t in tasks:
        work, protected = day_frame(schedule[(t.persona_id, t.day)])
        assert work["start"] <= t.planned_start and t.planned_end <= work["end"]
        for b in protected:
            assert not (to_minutes(b["start"]) < to_minutes(t.planned_end) and to_minutes(t.planned_start) < to_minutes(b["end"]))


def test_day_frame_examples(data):
    _, _, schedule = data
    work, protected = day_frame(schedule[("P01", 25)])
    assert work == {"start": "17:50", "end": "23:00"}
    assert {"id": "s3", "label": "Module D online quiz", "start": "20:00", "end": "20:45"} in protected  # quiz beats the window
    assert {"id": "s1", "label": "Outside free time", "start": "18:50", "end": "19:00"} in protected  # gap between windows
    assert not any(b["label"].startswith("Bus") for b in protected)  # studying on the bus is allowed
    _, protected = day_frame(schedule[("P06", 25)])
    assert protected == [{"id": "s1", "label": "Dinner", "start": "21:00", "end": "21:30"}]  # dinner beats the window
    assert day_frame(schedule[("P03", 5)]) is None  # no study window that day


# --- special habits ---------------------------------------------------------------------------------------

def _plain(p):
    return dataclasses.replace(p, late_factor=1.0, late_from=None, after_night_shift_factor=1.0, title_drift=(),
                               long_task_factor=1.0, long_task_minutes=None)


def test_each_special_habit_changes_only_the_tasks_it_should(data):
    personas, tasks, schedule = data
    after_night = first_after_night_shift(tasks, personas, schedule)
    changed = {}
    for t in tasks:
        p = personas[t.persona_id]
        flag = (t.persona_id, t.task_id) in after_night
        delta = planted_log_drift(p, t, "planted", flag) - planted_log_drift(_plain(p), t, "planted", False)
        if abs(delta) > 1e-12:
            changed[(t.persona_id, t.task_id)] = delta

    expected = {}
    for t in tasks:
        key = (t.persona_id, t.task_id)
        if t.persona_id == "P01" and t.planned_start >= "21:30":
            expected[key] = math.log(1.10)
        if t.persona_id == "P07" and t.day in night_shift_days(schedule, "P07") and key in after_night:
            expected[key] = math.log(1.35)
        if t.persona_id == "P08" and t.title.startswith(("Module B assignment: section", "Lit review: write synthesis")):
            expected[key] = math.log(1.60) - math.log(personas["P08"].drift[t.type])
        if t.persona_id == "P09" and t.type in LONG_TASK_TYPES and t.estimated_minutes >= 180:
            expected[key] = math.log(1.30)
    assert changed.keys() == expected.keys()
    for key, delta in expected.items():
        assert changed[key] == pytest.approx(delta)
    by_persona = {pid: sum(k[0] == pid for k in changed) for pid in ("P01", "P07", "P08", "P09")}
    assert by_persona["P01"] > 0 and by_persona["P07"] > 0 and by_persona["P08"] > 0
    # P09's longest Digital task in this task list is 130 min, so the ≥ 180 min habit never applies.
    assert by_persona["P09"] == 0
    assert max(t.estimated_minutes for t in tasks if t.persona_id == "P09" and t.type == "Digital") < 180


def test_after_night_shift_needs_a_schedule(data):
    personas, tasks, _ = data
    assert first_after_night_shift(tasks, personas, None) == set()


def test_p07_first_task_after_each_night_shift(data):
    personas, tasks, schedule = data
    after_night = first_after_night_shift(tasks, personas, schedule)
    firsts = sorted((t.day, t.task_id) for t in tasks if t.persona_id == "P07" and ("P07", t.task_id) in after_night)
    nights = night_shift_days(schedule, "P07")
    days_with_tasks = sorted(d for d in nights if any(t.persona_id == "P07" and t.day == d for t in tasks))
    assert [d for d, _ in firsts] == days_with_tasks
    for day, task_id in firsts:
        same_day = [t for t in tasks if t.persona_id == "P07" and t.day == day]
        assert min(same_day, key=lambda t: t.planned_start).task_id == task_id


# --- layer C and reproducibility -------------------------------------------------------------------------------

@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_disruptions_can_start_at_any_time_of_day(data, seed):
    # Owner, 14 Oct 2026: disruptions happen naturally, at any time, even in protected time.
    personas, tasks, schedule = data
    world = generate(personas, tasks, seed, schedule=schedule)
    starts = [to_minutes(d.start) for d in world.disruptions.values()]
    assert all(m % 15 == 0 and 0 <= m < 24 * 60 for m in starts)
    outside_free = [key for key, d in world.disruptions.items() if not free_minutes(schedule[key])[to_minutes(d.start)]]
    assert outside_free, "some disruptions start during work, sleep, travel, …"
    assert min(starts) < 6 * 60 and max(starts) >= 18 * 60  # night and evening alike


def test_a_disruption_matters_only_when_it_overlaps_a_planned_task(data, events):
    world, built, skipped = events
    by_day = {}
    for t in data[1]:
        by_day.setdefault((t.persona_id, t.day), []).append(t)

    def overlap(key):
        d = world.disruptions[key]
        s, e = to_minutes(d.start), min(to_minutes(d.start) + d.minutes, 24 * 60)
        return any(to_minutes(t.planned_start) < e and s < to_minutes(t.planned_end) for t in by_day.get(key, []))

    for e in built:
        assert overlap((e.persona_id, e.day))
    no_effect = [s for s in skipped if s.kind == "no_effect"]
    assert no_effect and all(not overlap((s.persona_id, s.day)) for s in no_effect)
    assert len(built) + len(skipped) == len(world.disruptions)  # every disruption is accounted for


def test_same_seed_same_output(data):
    personas, tasks, schedule = data
    a = generate(personas, tasks, 22, schedule=schedule)
    b = generate(personas, tasks, 22, schedule=schedule)
    assert (a.records, a.disruptions, a.actual_minutes) == (b.records, b.disruptions, b.actual_minutes)
    assert generate(personas, tasks, 23, schedule=schedule).records != a.records


def test_without_a_schedule_the_old_behaviour_is_kept(data):
    personas, tasks, _ = data
    world = generate(personas, tasks, 11)
    d = next(iter(world.disruptions.values()))
    data_input = engine_input(world, d.persona_id, d.day)
    assert data_input["workHours"] == {"start": "05:00", "end": "23:59"}  # the persona's own hours
    assert data_input["protectedBlocks"] == []


@pytest.fixture(scope="module")
def events(data):
    personas, tasks, schedule = data
    world = generate(personas, tasks, 11, schedule=schedule)
    built, skipped = build_events(world, n_estimators=10)
    return world, built, skipped


def test_scheduled_events_plan_only_in_free_study_time(events):
    world, built, _ = events
    assert built
    for e in built:
        free = free_minutes(world.schedule[(e.persona_id, e.day)])
        for t in e.raw["tasks"]:
            if t["start"] is not None:
                assert all(free[m] for m in range(to_minutes(t["start"]), to_minutes(t["end"]))), (e.persona_id, e.day, t["id"])
        assert event_metrics(world, e)["raw"]["ptvr"] == 0


def test_meeting_tasks_in_environment_disruptions_are_skipped_not_invented(events):
    _, _, skipped = events
    assert all("EF not defined" in s.reason for s in skipped if s.kind == "cannot_plan")


# --- loader errors ------------------------------------------------------------------------------------------------

HEADER = "personaId,day,date,kind,label,start,end"


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("P01,1,2026-09-07,nap,Nap,13:00,13:30", "line 2, column 'kind'"),
        ("P01,1,2026-09-08,sleep,Sleep,00:00,06:00", "line 2, column 'date'"),
        ("P01,1,2026-09-07,sleep,Sleep,06:00,05:00", "line 2, column 'end'"),
        ("P01,1,2026-09-07,sleep,Sleep,25:00,26:00", "line 2, column 'start'"),
        ("P99,1,2026-09-07,sleep,Sleep,00:00,06:00", "line 2, column 'personaId'"),
    ],
)
def test_schedule_loader_names_file_line_and_column(tmp_path, data, row, message):
    personas, _, _ = data
    path = tmp_path / "schedule.csv"
    path.write_text(f"{HEADER}\n{row}\n", encoding="utf-8")
    with pytest.raises(FormatError, match=f"schedule.csv {message}"):
        load_schedule(path, personas)


def test_24_00_is_accepted_as_an_end_time(tmp_path, data):
    personas, _, _ = data
    path = tmp_path / "schedule.csv"
    path.write_text(f"{HEADER}\nP01,1,2026-09-07,sleep,Sleep,23:30,24:00\n", encoding="utf-8")
    (block,) = load_schedule(path, personas)[("P01", 1)]
    assert (block.start, block.end) == (23 * 60 + 30, 24 * 60)


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("P01,1.10,,,,,", "column 'lateFrom'"),
        ("P01,,,,Module B=fast,,", "column 'titleDrift'"),
        ("P01,,,,,1.30,", "column 'longTaskMinutes'"),
        ("P42,1.10,21:30,,,,", "column 'personaId'"),
    ],
)
def test_habits_loader_names_file_line_and_column(tmp_path, row, message):
    path = tmp_path / "habits.csv"
    path.write_text("personaId,lateFactor,lateFrom,afterNightShiftFactor,titleDrift,longTaskFactor,longTaskMinutes\n"
                    f"{row}\n", encoding="utf-8")
    with pytest.raises(FormatError, match=f"habits.csv line 2, {message}"):
        load_habits(path, load_personas(PERSONAS))
