"""Layers B and C (SYNTHETIC): actual durations and disruptions, seeded.

Layer B: actual = estimate × planted drift × noise, where planted drift =
  base (persona.drift[type], or the title drift when the title matches)
  × eveningFactor (start ≥ 18:00) × weekendFactor (Sat/Sun)
  × lateFactor (start ≥ lateFrom) × longTaskFactor (Digital ≥ longTaskMinutes)
  × afterNightShiftFactor (first study task on a day after a night shift; needs a schedule)
  [× a hidden daily factor in the misspecified generator, which the model cannot see].
Layer C: per day, a confirmed disruption with probability DISRUPTION_RATE; with a
schedule its start is drawn only inside the day's study windows (never inside
work, campus, family or tutoring time). When it overlaps a task's planned slot,
the recorded span grows by the overlap (overlapMinutes), which the exclusion rule
(CLAUDE.md §3.6) must remove.
"""
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from components.c1_disruption.engine.time import to_hhmm, to_minutes
from components.c1_disruption.sim import settings
from components.c1_disruption.sim.personas import (
    Persona,
    PlannedTask,
    Schedule,
    free_minutes,
    night_shift_days,
)

EVENING_FROM = 18 * 60
LONG_TASK_TYPES = ("Digital",)  # longTaskFactor applies to Digital tasks (persona brief, P09)


@dataclass(frozen=True)
class Disruption:
    persona_id: str
    day: int
    type: str
    start: str
    minutes: int
    severity: int

    @property
    def end(self) -> str:
        return to_hhmm((to_minutes(self.start) + self.minutes) % (24 * 60))


@dataclass
class World:
    """Everything generated for one seed. `records` are Model 1 training records."""

    seed: int
    variant: str  # 'planted' / 'null' / 'misspecified'
    personas: dict[str, Persona]
    tasks: list[PlannedTask]
    schedule: Schedule | None = None
    actual_minutes: dict[tuple[str, str], float] = field(default_factory=dict)  # (persona, task) → true minutes
    disruptions: dict[tuple[str, int], Disruption] = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    dataset: str = settings.DATASET


def _start(persona: Persona, task: PlannedTask) -> int:
    return to_minutes(task.planned_start or persona.work_start)


def first_after_night_shift(tasks: list[PlannedTask], personas: dict[str, Persona], schedule: Schedule | None) -> set[tuple[str, str]]:
    """(persona, task) of the first study task (earliest planned start) on each day
    after a night shift. Empty without a schedule."""
    if not schedule:
        return set()
    out = set()
    for pid in personas:
        nights = night_shift_days(schedule, pid)
        for day in nights:
            same_day = [t for t in tasks if t.persona_id == pid and t.day == day]
            if same_day:
                first = min(same_day, key=lambda t: (_start(personas[pid], t), t.task_id))
                out.add((pid, first.task_id))
    return out


def planted_log_drift(persona: Persona, task: PlannedTask, variant: str, after_night_shift: bool = False) -> float:
    if variant == "null":
        return 0.0
    start = _start(persona, task)
    weekend = date.fromisoformat(task.date).weekday() >= 5
    base = next((d for prefix, d in persona.title_drift if task.title.startswith(prefix)), persona.drift[task.type])
    late = persona.late_from is not None and start >= to_minutes(persona.late_from)
    long_task = (persona.long_task_minutes is not None and task.type in LONG_TASK_TYPES
                 and task.estimated_minutes >= persona.long_task_minutes)
    return (
        math.log(base)
        + (math.log(persona.evening_factor) if start >= EVENING_FROM else 0.0)
        + (math.log(persona.weekend_factor) if weekend else 0.0)
        + (math.log(persona.late_factor) if late else 0.0)
        + (math.log(persona.long_task_factor) if long_task else 0.0)
        + (math.log(persona.after_night_shift_factor) if after_night_shift else 0.0)
    )


def _draw_minutes(rng: np.random.Generator) -> int:
    lo, hi = settings.DISRUPTION_MINUTES
    return int(rng.integers(lo // 15, hi // 15 + 1)) * 15


def _draw_type(rng: np.random.Generator) -> str:
    types = list(settings.DISRUPTION_MIX)
    return types[rng.choice(len(types), p=np.array(list(settings.DISRUPTION_MIX.values())))]


def _disruption(rng: np.random.Generator, persona: Persona, day: int, schedule: Schedule | None) -> Disruption | None:
    # Draw order type → minutes → start → severity, as before schedules existed, so a
    # seed without a schedule gives exactly the same disruptions as earlier versions.
    kind = _draw_type(rng)
    minutes = _draw_minutes(rng)
    if schedule is not None:
        # Start on a 15-minute step at which the student is free to study.
        free = free_minutes(schedule.get((persona.persona_id, day), []))
        starts = [m for m in range(0, 24 * 60, 15) if free[m]]
        if not starts:
            int(rng.integers(1, 4))  # keep the stream aligned with days that have study time
            return None  # no study time that day: nothing to disrupt
        start = starts[int(rng.integers(len(starts)))]
    else:
        lo = to_minutes(persona.work_start)
        hi = max(lo, to_minutes(persona.work_end) - 30)
        start = int(rng.integers(lo // 15, hi // 15 + 1)) * 15
    severity = int(rng.integers(1, 4))
    return Disruption(persona.persona_id, day, kind, to_hhmm(start), minutes, severity)


def _overlap(task: PlannedTask, d: Disruption | None) -> int:
    if d is None or not task.planned_start:
        return 0
    a, b = to_minutes(task.planned_start), to_minutes(task.planned_end)
    s = to_minutes(d.start)
    e = min(s + d.minutes, 24 * 60)
    return max(0, min(b, e) - max(a, s))


def generate(
    personas: dict[str, Persona], tasks: list[PlannedTask], seed: int, variant: str = "planted",
    schedule: Schedule | None = None,
) -> World:
    if variant not in ("planted", "null", "misspecified"):
        raise ValueError(f"Unknown variant '{variant}'")
    # One random stream per layer, so every variant of a seed has the SAME disruptions
    # and the SAME noise; only the planted drift differs (a paired comparison).
    rng_disruptions = np.random.default_rng([seed, 1])
    rng_noise = np.random.default_rng([seed, 2])
    rng_hidden = np.random.default_rng([seed, 3])
    world = World(seed, variant, personas, tasks, schedule)
    days = sorted({(t.persona_id, t.day) for t in tasks})
    hidden = {key: rng_hidden.normal(0, settings.HIDDEN_DAILY_SD) for key in days} if variant == "misspecified" else {}
    for key in days:  # layer C
        if rng_disruptions.random() < settings.DISRUPTION_RATE:
            d = _disruption(rng_disruptions, personas[key[0]], key[1], schedule)
            if d is not None:
                world.disruptions[key] = d
    after_night = first_after_night_shift(tasks, personas, schedule)
    for task in tasks:  # layer B
        persona = personas[task.persona_id]
        log_drift = (planted_log_drift(persona, task, variant, (task.persona_id, task.task_id) in after_night)
                     + hidden.get((task.persona_id, task.day), 0.0))
        actual = task.estimated_minutes * math.exp(log_drift + rng_noise.normal(0, persona.noise_sd))
        world.actual_minutes[(task.persona_id, task.task_id)] = actual
        overlap = _overlap(task, world.disruptions.get((task.persona_id, task.day)))
        world.records.append({
            "studentId": task.persona_id, "taskType": task.type, "priority": task.priority,
            "estimatedMinutes": float(task.estimated_minutes), "actualMinutes": round(actual + overlap, 1),
            "overlapMinutes": float(overlap), "date": task.date,
            "startHour": _start(persona, task) // 60,
            "taskId": task.task_id, "dataset": settings.DATASET,
        })
    return world
