"""Layer C from a per-persona disruption profile (planning chat, 14 Oct 2026).

Profile file (sim/data/SYNTHETIC_disruption_profile.csv), one row per persona and
disruption pattern:
  personaId, type            who, and which disruption type
  perWeekMin, perWeekMax     how often: each week a rate r is drawn from [min, max];
                             the count is floor(r) plus one more with probability
                             frac(r) (so "2-3/wk" gives 2 or 3, "1 per 2 wks" gives
                             0 or 1); the last, shorter week is scaled by its days/7
  days                       any | weekday | weekend | day names, e.g. Tue;Thu
  timeFrom, timeTo           start between these times (5-minute steps; equal = exact)
  during                     optional schedule kind the start must fall inside (e.g. bus)
  onDaysWith                 optional: only days whose schedule has a block with this label
  minMinutes, maxMinutes     duration (5-minute steps)
  source                     the planning-chat wording, kept for traceability
Severity is random 1-3.

Top-up: when a persona has fewer than TOP_UP_TARGET disruptions that overlap a planned
task (not counting types the engine can never plan, see NEVER_PLANNABLE), more are drawn
from that persona's own profile until the target is met.
"""
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from components.c1_disruption.engine import config as engine_config
from components.c1_disruption.engine.time import to_hhmm
from components.c1_disruption.sim.personas import (
    FormatError,
    Persona,
    PlannedTask,
    Schedule,
    _fail,
    _number,
    _rows,
    _time,
    day_to_date,
)

TOP_UP_TARGET = 10
MAX_TOP_UP_DRAWS = 5000  # per persona; a shortfall is reported, never looped forever
STEP = 5  # minutes, for start times and durations
DAY_NAMES = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# All EF values of these types are None (open research decision), so their events can
# never be planned; they are drawn, skipped and counted, but do not count towards the top-up.
NEVER_PLANNABLE = tuple(
    t for t, row in engine_config.ENV_FEASIBILITY.items() if all(v is None for v in row.values())
)


@dataclass(frozen=True)
class ProfileRow:
    persona_id: str
    type: str
    per_week_min: float
    per_week_max: float
    days: frozenset[int]  # weekday numbers, Monday = 0
    time_from: int
    time_to: int
    during: str | None
    on_days_with: str | None
    min_minutes: int
    max_minutes: int
    source: str

    @property
    def mean_rate(self) -> float:
        return (self.per_week_min + self.per_week_max) / 2


def _days(path: Path, line: int, text: str) -> frozenset[int]:
    text = text.strip() or "any"
    if text == "any":
        return frozenset(range(7))
    if text == "weekday":
        return frozenset(range(5))
    if text == "weekend":
        return frozenset({5, 6})
    names = [n.strip() for n in text.split(";")]
    if not all(n in DAY_NAMES for n in names):
        raise _fail(path, line, "days", f"'{text}' must be any, weekday, weekend or day names like Tue;Thu")
    return frozenset(DAY_NAMES.index(n) for n in names)


def load_profile(path: str | Path, personas: dict[str, Persona]) -> list[ProfileRow]:
    path = Path(path)
    rows: list[ProfileRow] = []
    for line, row in _rows(path):
        pid = row.get("personaId", "")
        if pid not in personas:
            raise _fail(path, line, "personaId", f"'{pid}' is not in the personas file")
        if row.get("type") not in engine_config.DISRUPTION_KINDS:
            raise _fail(path, line, "type", f"must be one of: {', '.join(engine_config.DISRUPTION_KINDS)}")
        lo = _number(path, line, row, "perWeekMin", 0, positive=False)
        hi = _number(path, line, row, "perWeekMax", lo, positive=False)
        if lo < 0 or hi < lo:
            raise _fail(path, line, "perWeekMax", "need 0 <= perWeekMin <= perWeekMax")
        t_from, t_to = _time(path, line, row, "timeFrom"), _time(path, line, row, "timeTo")
        if t_to < t_from:
            raise _fail(path, line, "timeTo", "must not be before timeFrom")
        d_min = _number(path, line, row, "minMinutes", 0)
        d_max = _number(path, line, row, "maxMinutes", d_min)
        if d_max < d_min or d_min != int(d_min) or d_max != int(d_max):
            raise _fail(path, line, "maxMinutes", "need whole minutes with minMinutes <= maxMinutes")
        rows.append(ProfileRow(
            persona_id=pid, type=row["type"], per_week_min=lo, per_week_max=hi,
            days=_days(path, line, row.get("days", "")),
            time_from=int(t_from[:2]) * 60 + int(t_from[3:]), time_to=int(t_to[:2]) * 60 + int(t_to[3:]),
            during=row.get("during") or None, on_days_with=row.get("onDaysWith") or None,
            min_minutes=int(d_min), max_minutes=int(d_max), source=row.get("source", ""),
        ))
    if not rows:
        raise FormatError(f"{path.name}: no profile rows")
    return rows


def _weekday(day: int) -> int:
    from datetime import date

    return date.fromisoformat(day_to_date(day)).weekday()


def candidate_starts(row: ProfileRow, day: int, schedule: Schedule | None) -> list[int]:
    """Start minutes (5-minute steps) allowed by the row on this day; empty = not eligible."""
    if _weekday(day) not in row.days:
        return []
    blocks = (schedule or {}).get((row.persona_id, day), [])
    if row.on_days_with and not any(row.on_days_with in b.label for b in blocks):
        return []
    starts = range(row.time_from - row.time_from % STEP, row.time_to + 1, STEP)
    if row.time_from == row.time_to:
        starts = range(row.time_from, row.time_from + 1)
    if row.during:
        inside = [b for b in blocks if b.kind == row.during]
        return [m for m in starts if any(b.start <= m < b.end for b in inside)]
    return list(starts)


def _duration(rng: np.random.Generator, row: ProfileRow) -> int:
    lo, hi = row.min_minutes // STEP, row.max_minutes // STEP
    return int(rng.integers(lo, hi + 1)) * STEP if hi > lo else row.min_minutes


def _week_count(rng: np.random.Generator, row: ProfileRow, share: float) -> int:
    rate = rng.uniform(row.per_week_min, row.per_week_max) * share
    return math.floor(rate) + (1 if rng.random() < rate - math.floor(rate) else 0)


def draw(rng: np.random.Generator, row: ProfileRow, days: list[int], schedule: Schedule | None):
    """One disruption for the row on a random eligible day among `days`, or None."""
    eligible = [(d, s) for d in days if (s := candidate_starts(row, d, schedule))]
    if not eligible:
        return None
    day, starts = eligible[int(rng.integers(len(eligible)))]
    start = starts[int(rng.integers(len(starts)))]
    return day, row.type, to_hhmm(start), _duration(rng, row), int(rng.integers(1, 4))


def overlaps_planned_task(tasks_by_day: dict[tuple[str, int], list[PlannedTask]], persona_id: str, day: int,
                          start: int, minutes: int) -> bool:
    end = min(start + minutes, 24 * 60)
    return any(
        t.planned_start and int(t.planned_start[:2]) * 60 + int(t.planned_start[3:]) < end
        and start < int(t.planned_end[:2]) * 60 + int(t.planned_end[3:])
        for t in tasks_by_day.get((persona_id, day), [])
    )


def draw_profile(rng: np.random.Generator, personas: dict[str, Persona], tasks: list[PlannedTask],
                 profile: list[ProfileRow], schedule: Schedule | None) -> tuple[list[tuple], dict[str, dict]]:
    """All disruptions for every persona: weekly draws, then the top-up.

    Returns (disruptions, report) with disruptions as (persona, day, type, start, minutes,
    severity, topUp) and report[persona] = {"drawn", "topUp", "effective", "shortfall"}.
    """
    all_days = sorted({t.day for t in tasks})
    last_day = max(all_days) if all_days else 0
    tasks_by_day: dict[tuple[str, int], list[PlannedTask]] = {}
    for t in tasks:
        tasks_by_day.setdefault((t.persona_id, t.day), []).append(t)
    out: list[tuple] = []
    report: dict[str, dict] = {}
    for pid in sorted(personas):
        rows = [r for r in profile if r.persona_id == pid]
        if not rows:
            continue
        drawn: list[tuple] = []
        for row in rows:  # weekly draws
            for week_start in range(1, last_day + 1, 7):
                week = [d for d in range(week_start, min(week_start + 7, last_day + 1))]
                for _ in range(_week_count(rng, row, len(week) / 7)):
                    d = draw(rng, row, week, schedule)
                    if d is not None:
                        drawn.append((pid, *d, False))

        def effective(items):
            return sum(1 for (_, day, kind, start, minutes, _, _) in items if kind not in NEVER_PLANNABLE
                       and overlaps_planned_task(tasks_by_day, pid, day, int(start[:2]) * 60 + int(start[3:]), minutes))

        weights = np.array([r.mean_rate for r in rows], dtype=float)
        weights = weights / weights.sum() if weights.sum() > 0 else np.full(len(rows), 1 / len(rows))
        top_up, attempts = 0, 0
        count = effective(drawn)
        while count < TOP_UP_TARGET and attempts < MAX_TOP_UP_DRAWS:
            attempts += 1
            row = rows[int(rng.choice(len(rows), p=weights))]
            d = draw(rng, row, all_days, schedule)
            if d is None:
                continue
            drawn.append((pid, *d, True))
            top_up += 1
            count = effective(drawn)
        out.extend(drawn)
        report[pid] = {"drawn": len(drawn) - top_up, "topUp": top_up, "effective": count,
                       "shortfall": max(0, TOP_UP_TARGET - count)}
    return out, report
