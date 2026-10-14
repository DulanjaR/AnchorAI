"""Layer D (SYNTHETIC): MVDs for every simulated disruption, raw vs corrected, and
simulated decisions for Model 2.

For each disruption event (persona, day, n):
  raw MVD        engine on the student's own estimates (model off)
  corrected MVD  engine on Model 1's corrected durations (model on); the model is
                 trained only on records from days BEFORE the event's week
                 (weekly retraining, so no event sees its own or later data)
Replanning scope (approved, planning chat 14 Oct 2026): tasks planned to end before
the disruption starts are done and left out; a task in progress at the start is
replanned for its remaining minutes only (its estimate, corrected duration and true
duration are scaled by the remaining share of its planned slot).
Several disruptions on one day are each planned on their own, against that day's
original plan (PROPOSED).
Simulated completion (approved): a placed task is done when its true minutes are ≤
the minutes the engine planned with (for a Reduce task the shortened portion takes
proportionally less time, so the same test applies).
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.mvd import generate_mvd
from components.c1_disruption.engine.overload import check_overload
from components.c1_disruption.engine.time import to_minutes
from components.c1_disruption.metrics import plan_metrics as m
from components.c1_disruption.ml.drift.data import clean
from components.c1_disruption.ml.drift.model import DriftModel
from components.c1_disruption.sim import settings
from components.c1_disruption.sim.generate import World
from components.c1_disruption.sim.personas import day_frame

Key = tuple[str, int, int]  # (persona, day, n)

NO_EFFECT = "no_effect"
CANNOT_PLAN = "cannot_plan"


@dataclass
class Event:
    persona_id: str
    day: int
    date: str
    engine_input: dict[str, Any]  # raw (estimates; in-progress tasks: remaining minutes)
    raw: dict[str, Any]  # MVD, model off
    corrected: dict[str, Any] | None  # MVD, model on (None before the model has any training data)
    severity: int
    slack_ratio: float | None
    index: int = 0
    remaining: dict[str, float] = field(default_factory=dict)  # task → share still to do (1.0 = all)
    done_before: list[str] = field(default_factory=list)  # tasks finished before the disruption


@dataclass
class Skipped:
    """A disruption that produced no MVD, counted and reported:
      no_effect    it overlaps none of the day's planned tasks, so nothing changes
      cannot_plan  the engine cannot plan it, e.g. a None EF value (open research
                   decision); never given an invented value
    """

    persona_id: str
    day: int
    reason: str
    kind: str = CANNOT_PLAN
    index: int = 0
    type: str = ""


def _week_start(day_str: str) -> str:
    d = date.fromisoformat(day_str)
    return (d - timedelta(days=d.weekday())).isoformat()


def day_frame_for(world: World, persona_id: str, day: int) -> tuple[dict[str, str], list[dict[str, str]]]:
    """Work hours and protected blocks of one day: from the schedule when there is one
    (personas.day_frame: free-time windows only), otherwise the persona's fixed day."""
    if world.schedule is not None:
        frame = day_frame(world.schedule.get((persona_id, day), []))
        if frame is not None:
            return frame
    persona = world.personas[persona_id]
    return {"start": persona.work_start, "end": persona.work_end}, [dict(b) for b in persona.protected_blocks]


def _key(world: World, key: Key | tuple[str, int]) -> Key:
    return key if len(key) == 3 else (*key, 0)  # (persona, day) = the day's first disruption


def overlaps_a_task(world: World, *key) -> bool:
    """A disruption affects the day only when its window (clipped at midnight, as in
    the engine) overlaps the planned slot of at least one task (owner, 14 Oct 2026).
    Tasks without a planned slot cannot overlap anything."""
    pid, day, n = _key(world, tuple(key))
    d = world.disruptions[(pid, day, n)]
    start = to_minutes(d.start)
    end = min(start + d.minutes, 24 * 60)
    return any(
        t.persona_id == pid and t.day == day and t.planned_start
        and to_minutes(t.planned_start) < end and start < to_minutes(t.planned_end)
        for t in world.tasks
    )


def replan_scope(world: World, key: Key) -> tuple[list, dict[str, float], list[str]]:
    """(tasks to replan, remaining share per task, tasks already done) at the disruption start."""
    pid, day, n = key
    start = to_minutes(world.disruptions[key].start)
    keep, share, done = [], {}, []
    for t in (t for t in world.tasks if t.persona_id == pid and t.day == day):
        if t.planned_start and to_minutes(t.planned_end) <= start:
            done.append(t.task_id)  # planned to end before the disruption: done
            continue
        if t.planned_start and to_minutes(t.planned_start) < start:
            slot = to_minutes(t.planned_end) - to_minutes(t.planned_start)
            share[t.task_id] = (to_minutes(t.planned_end) - start) / slot  # in progress: the rest only
        else:
            share[t.task_id] = 1.0
        keep.append(t)
    return keep, share, done


def engine_input(world: World, *key) -> dict[str, Any]:
    key = _key(world, tuple(key))
    pid, day, _ = key
    d = world.disruptions[key]
    tasks, share, _ = replan_scope(world, key)
    work_hours, protected = day_frame_for(world, pid, day)
    any_task = next(t for t in world.tasks if t.persona_id == pid and t.day == day)
    return {
        "date": any_task.date,
        "workHours": work_hours,
        "planFrom": max(d.start, work_hours["start"]),  # the student replans when the disruption starts
        "disruption": {"type": d.type, "start": d.start, "end": d.end},
        "protectedBlocks": protected,
        "tasks": [
            {"id": t.task_id, "title": t.title, "type": t.type, "priority": t.priority,
             "estimatedHours": t.estimated_minutes * share[t.task_id] / 60, "deadline": t.deadline,
             "delegable": t.delegable, "plannedStart": t.planned_start}
            for t in tasks
        ],
    }


def _corrected_input(data: dict[str, Any], model: DriftModel, persona_id: str, share: dict[str, float]) -> dict[str, Any]:
    full = {t["id"]: t["estimatedHours"] * 60 / share[t["id"]] for t in data["tasks"]}  # the task's whole estimate
    queries = [{"studentId": persona_id, "taskType": t["type"], "priority": t["priority"],
                "estimatedMinutes": full[t["id"]], "date": data["date"],
                "startHour": int((t.get("plannedStart") or data["workHours"]["start"])[:2])} for t in data["tasks"]]
    tasks = []
    for t, p in zip(data["tasks"], model.predict(queries)):
        point, low, high = (v * share[t["id"]] / 60 for v in p.corrected_minutes(full[t["id"]]))
        tasks.append({**t, "estimatedHours": point, "estimatedHoursLow": min(low, point), "estimatedHoursHigh": max(high, point)})
    return {**data, "tasks": tasks}


def build_events(world: World, n_estimators: int = settings.SIM_N_ESTIMATORS) -> tuple[list[Event], list[Skipped]]:
    models: dict[str, DriftModel | None] = {}  # week start → model trained on earlier records
    events: list[Event] = []
    skipped: list[Skipped] = []
    for key in sorted(world.disruptions):
        pid, day, n = key
        d = world.disruptions[key]
        if not overlaps_a_task(world, *key):
            skipped.append(Skipped(pid, day, "overlaps no planned task", NO_EFFECT, n, d.type))
            continue
        data = engine_input(world, *key)
        _, share, done = replan_scope(world, key)
        try:
            raw = generate_mvd(data)
        except EngineError as err:
            skipped.append(Skipped(pid, day, str(err), CANNOT_PLAN, n, d.type))
            continue
        cutoff = _week_start(data["date"])
        if cutoff not in models:
            train = clean([r for r in world.records if r["date"] < cutoff])
            models[cutoff] = DriftModel(n_estimators=n_estimators).fit(train) if len(train) >= 10 else None
        model = models[cutoff]
        normal_day = {k: v for k, v in data.items() if k != "disruption"}
        events.append(Event(
            persona_id=pid, day=day, date=data["date"], engine_input=data, raw=raw,
            corrected=generate_mvd(_corrected_input(data, model, pid, share)) if model else None,
            severity=d.severity, slack_ratio=check_overload(normal_day)["slackRatio"],
            index=n, remaining=share, done_before=done,
        ))
    return events, skipped


def _true_minutes(world: World, event: Event, task_id: str) -> float:
    return world.actual_minutes[(event.persona_id, task_id)] * event.remaining.get(task_id, 1.0)


def _outcomes(world: World, event: Event, mvd: dict[str, Any]) -> tuple[dict[str, str], dict[str, float]]:
    outcomes, actual = {}, {}
    for t in mvd["tasks"]:
        true = _true_minutes(world, event, t["id"])
        actual[t["id"]] = true
        if t["tag"] in m.PLACED_TAGS:
            outcomes[t["id"]] = "done" if true <= t["estimatedHours"] * 60 else "not_done"
    return outcomes, actual


def event_metrics(world: World, event: Event) -> dict[str, Any]:
    """Raw vs corrected for the SAME event (docs/METHODOLOGY.md §5, D-EVAL)."""
    blocks = event.engine_input["protectedBlocks"]
    row: dict[str, Any] = {
        "personaId": event.persona_id, "date": event.date, "tightSlack": m.is_tight_slack(event.slack_ratio),
        "dataset": settings.DATASET,
    }
    true_hours = {t["id"]: _true_minutes(world, event, t["id"]) / 60 for t in event.raw["tasks"]}
    for name, mvd in (("raw", event.raw), ("corrected", event.corrected)):
        if mvd is None:
            continue
        outcomes, actual = _outcomes(world, event, mvd)
        row[name] = {
            "ctrrPlanned": m.ctrr_planned(mvd),
            "ctrrRealised": m.ctrr_realised(mvd, outcomes),
            "ptvr": m.ptvr(mvd, blocks),
            "feasibilityTrue": m.feasibility(mvd, true_hours),
            "realisedFeasibility": m.realised_feasibility(mvd, actual),
            "planCompletionRate": m.plan_completion_rate(mvd, outcomes),
        }
    if event.corrected is not None:
        row["decisionChangeRate"] = m.decision_change_rate(event.raw, event.corrected)
    return row
