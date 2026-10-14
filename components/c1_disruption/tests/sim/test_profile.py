"""Disruption profile (layer C) and the replanning scope (planning chat, 14 Oct 2026).
All data SYNTHETIC."""
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from components.c1_disruption.engine.time import to_minutes
from components.c1_disruption.sim.events import build_events, engine_input, event_metrics, replan_scope
from components.c1_disruption.sim.generate import Disruption, World, generate
from components.c1_disruption.sim.personas import (
    FormatError,
    Persona,
    PlannedTask,
    load_personas,
    load_schedule,
    load_tasks,
)
from components.c1_disruption.sim.profile import (
    NEVER_PLANNABLE,
    TOP_UP_TARGET,
    _weekday,
    candidate_starts,
    draw_profile,
    load_profile,
    overlaps_planned_task,
)

DATA = Path(__file__).parents[2] / "sim" / "data"


@pytest.fixture(scope="module")
def data():
    personas = load_personas(DATA / "SYNTHETIC_personas.csv", DATA / "SYNTHETIC_habits.csv")
    tasks = load_tasks(DATA / "SYNTHETIC_tasks_planned.csv", personas)
    schedule = load_schedule(DATA / "SYNTHETIC_schedule.csv", personas)
    return personas, tasks, schedule, load_profile(DATA / "SYNTHETIC_disruption_profile.csv", personas)


def test_profile_loads_one_or_more_rows_for_every_persona(data):
    personas, _, _, profile = data
    assert len(profile) == 18
    assert {r.persona_id for r in profile} == set(personas)
    assert NEVER_PLANNABLE == ("connectivity_failure",)
    p09 = next(r for r in profile if r.persona_id == "P09" and r.type == "urgent_work")
    assert (p09.days, p09.time_from, p09.time_to, p09.min_minutes, p09.max_minutes) == (frozenset({1, 3}), 1230, 1230, 30, 60)
    p05 = next(r for r in profile if r.persona_id == "P05")
    assert (p05.type, p05.during, p05.per_week_min, p05.per_week_max) == ("transport_delay", "bus", 2, 3)


def _tasks_by_day(tasks):
    out = {}
    for t in tasks:
        out.setdefault((t.persona_id, t.day), []).append(t)
    return out


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_every_disruption_follows_its_persona_profile(data, seed):
    personas, tasks, schedule, profile = data
    drawn, _ = draw_profile(np.random.default_rng([seed, 1]), personas, tasks, profile, schedule)
    for pid, day, kind, start, minutes, severity, _ in drawn:
        rows = [r for r in profile if r.persona_id == pid and r.type == kind]
        m = to_minutes(start)
        assert any(m in candidate_starts(r, day, schedule) and r.min_minutes <= minutes <= r.max_minutes for r in rows), \
            (pid, day, kind, start, minutes)
        assert severity in (1, 2, 3)


def test_weekly_counts_follow_the_rate(data):
    personas, tasks, schedule, profile = data
    drawn, _ = draw_profile(np.random.default_rng([11, 1]), personas, tasks, profile, schedule)
    weekly = [d for d in drawn if not d[6]]  # without the top-up
    for week in range(4):  # the four full weeks
        in_week = Counter((d[0], d[2]) for d in weekly if 7 * week < d[1] <= 7 * week + 7)
        assert in_week[("P03", "urgent_work")] == 2  # 2/wk
        assert in_week[("P06", "family_obligation")] == 3  # 3/wk
        assert 2 <= in_week[("P01", "power_outage")] <= 3  # 2–3/wk
        assert in_week[("P09", "urgent_work")] <= 1  # 1/wk, Tue/Thu only
    p01_weekday = [d for d in weekly if d[0] == "P01" and d[2] == "power_outage"]
    assert all(_weekday(d[1]) < 5 and "18:30" <= d[3] <= "21:30" for d in p01_weekday)


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
def test_top_up_gives_every_persona_10_effective_disruptions(data, seed):
    personas, tasks, schedule, profile = data
    drawn, report = draw_profile(np.random.default_rng([seed, 1]), personas, tasks, profile, schedule)
    by_day = _tasks_by_day(tasks)
    for pid in personas:
        effective = sum(1 for d in drawn if d[0] == pid and d[2] not in NEVER_PLANNABLE
                        and overlaps_planned_task(by_day, pid, d[1], to_minutes(d[3]), d[4]))
        assert effective == report[pid]["effective"] >= TOP_UP_TARGET
        assert report[pid]["shortfall"] == 0
        assert report[pid]["topUp"] == sum(1 for d in drawn if d[0] == pid and d[6])


def test_connectivity_failures_are_skipped_and_counted(data):
    personas, tasks, schedule, profile = data
    world = generate(personas, tasks, 11, schedule=schedule, profile=profile)
    events, skipped = build_events(world, n_estimators=10)
    assert all(e.engine_input["disruption"]["type"] != "connectivity_failure" for e in events)
    connectivity = [s for s in skipped if s.type == "connectivity_failure"]
    assert connectivity and {s.kind for s in connectivity} <= {"no_effect", "cannot_plan"}
    assert all("connectivity_failure" in s.reason for s in connectivity if s.kind == "cannot_plan")
    assert len(events) + len(skipped) == len(world.disruptions)


def test_same_seed_same_disruptions(data):
    personas, tasks, schedule, profile = data
    a = generate(personas, tasks, 33, schedule=schedule, profile=profile)
    b = generate(personas, tasks, 33, schedule=schedule, profile=profile)
    assert a.disruptions == b.disruptions and a.profile_report == b.profile_report
    assert generate(personas, tasks, 34, schedule=schedule, profile=profile).disruptions != a.disruptions


@pytest.mark.parametrize(
    ("row", "message"),
    [
        ("P01,flood,1,1,any,18:00,20:00,,,30,60,x", "column 'type'"),
        ("P01,power_outage,1,1,Funday,18:00,20:00,,,30,60,x", "column 'days'"),
        ("P01,power_outage,1,1,any,20:00,18:00,,,30,60,x", "column 'timeTo'"),
        ("P01,power_outage,3,1,any,18:00,20:00,,,30,60,x", "column 'perWeekMax'"),
        ("P77,power_outage,1,1,any,18:00,20:00,,,30,60,x", "column 'personaId'"),
    ],
)
def test_profile_loader_names_file_line_and_column(tmp_path, data, row, message):
    personas = data[0]
    header = (DATA / "SYNTHETIC_disruption_profile.csv").read_text(encoding="utf-8").splitlines()[0]
    path = tmp_path / "profile.csv"
    path.write_text(f"{header}\n{row}\n", encoding="utf-8")
    with pytest.raises(FormatError, match=f"profile.csv line 2, {message}"):
        load_profile(path, personas)


# --- replanning scope --------------------------------------------------------------------------

def small_world(start: str) -> World:
    """SYNTHETIC: one persona, three tasks 09:00–10:00, 10:00–12:00, 13:00–14:00."""
    persona = Persona("Z", "SYNTHETIC test", "08:00", "18:00")
    tasks = [PlannedTask("Z", 1, "a", "A", "Analog", "High", 60, 0, planned_start="09:00", planned_end="10:00"),
             PlannedTask("Z", 1, "b", "B", "Analog", "High", 120, 0, planned_start="10:00", planned_end="12:00"),
             PlannedTask("Z", 1, "c", "C", "Digital", "Medium", 60, 1, planned_start="13:00", planned_end="14:00")]
    world = World(1, "planted", {"Z": persona}, tasks)
    world.disruptions[("Z", 1, 0)] = Disruption("Z", 1, "transport_delay", start, 60, 2)
    world.actual_minutes = {("Z", "a"): 60.0, ("Z", "b"): 150.0, ("Z", "c"): 60.0}
    world.records = []
    return world


def test_tasks_that_ended_before_the_disruption_are_done_and_left_out():
    world = small_world("10:30")
    tasks, share, done = replan_scope(world, ("Z", 1, 0))
    assert done == ["a"]  # 09:00–10:00 ended before 10:30
    assert [t.task_id for t in tasks] == ["b", "c"]
    assert [t["id"] for t in engine_input(world, "Z", 1, 0)["tasks"]] == ["b", "c"]


def test_a_task_in_progress_is_replanned_for_its_remaining_minutes_only():
    world = small_world("10:30")
    _, share, _ = replan_scope(world, ("Z", 1, 0))
    assert share == {"b": 0.75, "c": 1.0}  # B: 90 of its 120 planned minutes are left
    hours = {t["id"]: t["estimatedHours"] for t in engine_input(world, "Z", 1, 0)["tasks"]}
    assert hours == {"b": 1.5, "c": 1.0}


def test_remaining_share_also_scales_the_true_minutes():
    world = small_world("10:30")
    events, _ = build_events(world, n_estimators=10)
    (event,) = events
    assert event.remaining["b"] == 0.75 and event.done_before == ["a"]
    from components.c1_disruption.sim.events import _outcomes

    outcomes, actual = _outcomes(world, event, event.raw)
    # B's true 150 min × 0.75 = 112.5 min against 90 planned remaining minutes → not done.
    # C (Medium, due tomorrow, Digital, EF 0.7): Fi = 1 × 2 / (1 × 0.7) = 2.86 > 2 → moved, not placed.
    assert actual == {"b": 112.5, "c": 60.0}
    assert outcomes == {"b": "not_done"}
    assert event_metrics(world, event)["raw"]["planCompletionRate"] == 0.0


def test_a_disruption_before_any_task_replans_everything():
    world = small_world("08:00")
    _, share, done = replan_scope(world, ("Z", 1, 0))
    assert done == [] and share == {"a": 1.0, "b": 1.0, "c": 1.0}
