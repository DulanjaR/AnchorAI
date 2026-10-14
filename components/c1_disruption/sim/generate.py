"""Layers B and C (SYNTHETIC): actual durations and disruptions, seeded.

Layer B: actual = estimate × planted drift × noise, where planted drift =
  persona.drift[type] × eveningFactor (start ≥ 18:00) × weekendFactor (Sat/Sun)
  [× a hidden daily factor in the misspecified generator, which the model cannot see].
Layer C: per day, a confirmed disruption with probability DISRUPTION_RATE; when it
overlaps a task's planned slot, the recorded span grows by the overlap
(overlapMinutes), which the exclusion rule (CLAUDE.md §3.6) must remove.
"""
import math
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from components.c1_disruption.engine.time import to_hhmm, to_minutes
from components.c1_disruption.sim import settings
from components.c1_disruption.sim.personas import Persona, PlannedTask


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
    actual_minutes: dict[tuple[str, str], float] = field(default_factory=dict)  # (persona, task) → true minutes
    disruptions: dict[tuple[str, int], Disruption] = field(default_factory=dict)
    records: list[dict] = field(default_factory=list)
    dataset: str = settings.DATASET


def planted_log_drift(persona: Persona, task: PlannedTask, variant: str) -> float:
    if variant == "null":
        return 0.0
    hour = to_minutes(task.planned_start or persona.work_start) // 60
    weekend = date.fromisoformat(task.date).weekday() >= 5
    return (
        math.log(persona.drift[task.type])
        + (math.log(persona.evening_factor) if hour >= 18 else 0.0)
        + (math.log(persona.weekend_factor) if weekend else 0.0)
    )


def _disruption(rng: np.random.Generator, persona: Persona, day: int) -> Disruption:
    types = list(settings.DISRUPTION_MIX)
    kind = types[rng.choice(len(types), p=np.array(list(settings.DISRUPTION_MIX.values())))]
    lo, hi = settings.DISRUPTION_MINUTES
    minutes = int(rng.integers(lo // 15, hi // 15 + 1)) * 15
    start_lo, start_hi = to_minutes(persona.work_start), max(to_minutes(persona.work_start), to_minutes(persona.work_end) - 30)
    start = int(rng.integers(start_lo // 15, start_hi // 15 + 1)) * 15
    return Disruption(persona.persona_id, day, kind, to_hhmm(start), minutes, int(rng.integers(1, 4)))


def _overlap(task: PlannedTask, d: Disruption | None) -> int:
    if d is None or not task.planned_start:
        return 0
    a, b = to_minutes(task.planned_start), to_minutes(task.planned_end)
    s = to_minutes(d.start)
    e = min(s + d.minutes, 24 * 60)
    return max(0, min(b, e) - max(a, s))


def generate(personas: dict[str, Persona], tasks: list[PlannedTask], seed: int, variant: str = "planted") -> World:
    if variant not in ("planted", "null", "misspecified"):
        raise ValueError(f"Unknown variant '{variant}'")
    # One random stream per layer, so every variant of a seed has the SAME disruptions
    # and the SAME noise; only the planted drift differs (a paired comparison).
    rng_disruptions = np.random.default_rng([seed, 1])
    rng_noise = np.random.default_rng([seed, 2])
    rng_hidden = np.random.default_rng([seed, 3])
    world = World(seed, variant, personas, tasks)
    days = sorted({(t.persona_id, t.day) for t in tasks})
    hidden = {key: rng_hidden.normal(0, settings.HIDDEN_DAILY_SD) for key in days} if variant == "misspecified" else {}
    for key in days:  # layer C
        if rng_disruptions.random() < settings.DISRUPTION_RATE:
            world.disruptions[key] = _disruption(rng_disruptions, personas[key[0]], key[1])
    for task in tasks:  # layer B
        persona = personas[task.persona_id]
        log_drift = planted_log_drift(persona, task, variant) + hidden.get((task.persona_id, task.day), 0.0)
        actual = task.estimated_minutes * math.exp(log_drift + rng_noise.normal(0, persona.noise_sd))
        world.actual_minutes[(task.persona_id, task.task_id)] = actual
        overlap = _overlap(task, world.disruptions.get((task.persona_id, task.day)))
        world.records.append({
            "studentId": task.persona_id, "taskType": task.type, "priority": task.priority,
            "estimatedMinutes": float(task.estimated_minutes), "actualMinutes": round(actual + overlap, 1),
            "overlapMinutes": float(overlap), "date": task.date,
            "startHour": to_minutes(task.planned_start or persona.work_start) // 60,
            "taskId": task.task_id, "dataset": settings.DATASET,
        })
    return world
