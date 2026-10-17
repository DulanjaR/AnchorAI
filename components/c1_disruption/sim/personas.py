"""Layer A: load and check the owner's persona, habit, task and schedule files
(format: sim/README.md). Every problem names the file, line and column."""
import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from components.c1_disruption.app.services.planning import STRATEGIES
from components.c1_disruption.engine import config as engine_config
from components.c1_disruption.ml.bandit.actions import ACTIONS
from components.c1_disruption.sim import settings
from components.c1_disruption.engine.time import is_time


class FormatError(ValueError):
    """A problem in an input file; the message names the file, line and column."""


@dataclass(frozen=True)
class Persona:
    persona_id: str
    label: str
    work_start: str
    work_end: str
    protected_blocks: tuple[dict, ...] = ()
    drift: dict[str, float] = field(default_factory=lambda: {t: 1.0 for t in engine_config.TASK_TYPES})
    evening_factor: float = 1.0
    weekend_factor: float = 1.0
    noise_sd: float = 0.10
    preferred_strategy: str = "default"
    # Special habits (planted drift beyond type / evening / weekend), from the habits file.
    late_factor: float = 1.0  # x for tasks starting at or after late_from
    late_from: str | None = None
    after_night_shift_factor: float = 1.0  # x for the first task on a day after a night shift
    title_drift: tuple[tuple[str, float], ...] = ()  # (title prefix, drift): replaces the type drift
    long_task_factor: float = 1.0  # x for Digital tasks of at least long_task_minutes
    long_task_minutes: int | None = None


@dataclass(frozen=True)
class PlannedTask:
    persona_id: str
    day: int
    task_id: str
    title: str
    type: str
    priority: str
    estimated_minutes: int
    deadline_in_days: int
    deadline_time: str = "23:59"
    planned_start: str | None = None
    planned_end: str | None = None
    delegable: bool = False
    category: str | None = None  # coding / writing / reading / revision (optional, 16 Oct 2026)

    @property
    def date(self) -> str:
        return day_to_date(self.day)

    @property
    def deadline(self) -> str:
        return f"{day_to_date(self.day + self.deadline_in_days)}T{self.deadline_time}"


def day_to_date(day: int) -> str:
    return (date.fromisoformat(settings.START_DATE) + timedelta(days=day - 1)).isoformat()


def _rows(path: Path) -> list[tuple[int, dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [(i, {k.strip(): (v or "").strip() for k, v in row.items() if k}) for i, row in enumerate(csv.DictReader(f), 2)]


def _fail(path: Path, line: int, column: str, message: str) -> FormatError:
    return FormatError(f"{path.name} line {line}, column '{column}': {message}")


def _number(path: Path, line: int, row: dict, column: str, default: float, positive: bool = True) -> float:
    text = row.get(column, "")
    if not text:
        return default
    try:
        value = float(text)
    except ValueError:
        raise _fail(path, line, column, f"'{text}' is not a number") from None
    if positive and value <= 0:
        raise _fail(path, line, column, f"must be positive, got {text}")
    return value


def _time(path: Path, line: int, row: dict, column: str, required: bool = True) -> str | None:
    text = row.get(column, "")
    if not text and not required:
        return None
    if not is_time(text):
        raise _fail(path, line, column, f"'{text}' is not a time HH:MM")
    return text


def _blocks(path: Path, line: int, text: str) -> tuple[dict, ...]:
    blocks = []
    for i, item in enumerate(p.strip() for p in text.split(";") if p.strip()):
        label, _, span = item.rpartition(" ")
        start, _, end = span.partition("-")
        if not label or not is_time(start) or not is_time(end) or start == end:
            raise _fail(path, line, "protectedBlocks", f"'{item}' is not 'label HH:MM-HH:MM'")
        blocks.append({"id": f"b{i + 1}", "label": label, "start": start, "end": end})
    return tuple(blocks)


def load_personas(path: str | Path, habits: str | Path | None = None) -> dict[str, Persona]:
    """Personas, with their special habits merged in from the habits file if given."""
    path = Path(path)
    personas: dict[str, Persona] = {}
    for line, row in _rows(path):
        pid = row.get("personaId", "")
        if not pid:
            raise _fail(path, line, "personaId", "is required")
        if pid in personas:
            raise _fail(path, line, "personaId", f"'{pid}' appears twice")
        if not row.get("label"):
            raise _fail(path, line, "label", "is required")
        start, end = _time(path, line, row, "workStart"), _time(path, line, row, "workEnd")
        if end <= start:
            raise _fail(path, line, "workEnd", "must be after workStart")
        strategy = row.get("preferredStrategy") or "default"
        if strategy not in ACTIONS:
            raise _fail(path, line, "preferredStrategy", f"must be one of: {', '.join(STRATEGIES)}")
        personas[pid] = Persona(
            persona_id=pid,
            label=row["label"],
            work_start=start,
            work_end=end,
            protected_blocks=_blocks(path, line, row.get("protectedBlocks", "")),
            drift={t: _number(path, line, row, f"drift{t}", 1.0) for t in engine_config.TASK_TYPES},
            evening_factor=_number(path, line, row, "eveningFactor", 1.0),
            weekend_factor=_number(path, line, row, "weekendFactor", 1.0),
            noise_sd=_number(path, line, row, "noiseSd", 0.10, positive=False),
            preferred_strategy=strategy,
        )
    if not personas:
        raise FormatError(f"{path.name}: no personas")
    return load_habits(habits, personas) if habits else personas


def _title_drift(path: Path, line: int, text: str) -> tuple[tuple[str, float], ...]:
    items = []
    for item in (p.strip() for p in text.split(";") if p.strip()):
        prefix, sep, value = item.rpartition("=")
        try:
            drift = float(value)
        except ValueError:
            drift = 0.0
        if not sep or not prefix.strip() or drift <= 0:
            raise _fail(path, line, "titleDrift", f"'{item}' is not 'title prefix=drift'")
        items.append((prefix.strip(), drift))
    return tuple(items)


def load_habits(path: str | Path, personas: dict[str, Persona]) -> dict[str, Persona]:
    """Special habits as explicit fields (sim/README.md): lateFactor + lateFrom,
    afterNightShiftFactor, titleDrift, longTaskFactor + longTaskMinutes."""
    path = Path(path)
    out = dict(personas)
    for line, row in _rows(path):
        pid = row.get("personaId", "")
        if pid not in personas:
            raise _fail(path, line, "personaId", f"'{pid}' is not in the personas file")
        late_from = _time(path, line, row, "lateFrom", required=False)
        late = _number(path, line, row, "lateFactor", 1.0)
        if (late != 1.0) != (late_from is not None):
            raise _fail(path, line, "lateFrom", "lateFactor and lateFrom go together")
        long_factor = _number(path, line, row, "longTaskFactor", 1.0)
        long_minutes = _number(path, line, row, "longTaskMinutes", 0, positive=False)
        if (long_factor != 1.0) != (long_minutes > 0) or long_minutes != int(long_minutes):
            raise _fail(path, line, "longTaskMinutes", "longTaskFactor and longTaskMinutes (whole minutes) go together")
        out[pid] = Persona(**{
            **personas[pid].__dict__,
            "late_factor": late,
            "late_from": late_from,
            "after_night_shift_factor": _number(path, line, row, "afterNightShiftFactor", 1.0),
            "title_drift": _title_drift(path, line, row.get("titleDrift", "")),
            "long_task_factor": long_factor,
            "long_task_minutes": int(long_minutes) or None,
        })
    return out


def load_tasks(path: str | Path, personas: dict[str, Persona]) -> list[PlannedTask]:
    path = Path(path)
    tasks: list[PlannedTask] = []
    seen: set[tuple[str, str]] = set()
    for line, row in _rows(path):
        pid = row.get("personaId", "")
        if pid not in personas:
            raise _fail(path, line, "personaId", f"'{pid}' is not in the personas file")
        task_id = row.get("taskId", "")
        if not task_id or (pid, task_id) in seen:
            raise _fail(path, line, "taskId", "is required and must be unique within the persona")
        seen.add((pid, task_id))
        for column, options in (("type", engine_config.TASK_TYPES), ("priority", tuple(engine_config.PRIORITY_SCORE))):
            if row.get(column) not in options:
                raise _fail(path, line, column, f"must be one of: {', '.join(options)}")
        if not row.get("title"):
            raise _fail(path, line, "title", "is required")
        day = _number(path, line, row, "day", 0)
        due = _number(path, line, row, "deadlineInDays", 0, positive=False)
        minutes = _number(path, line, row, "estimatedMinutes", 0)
        for column, value in (("day", day), ("deadlineInDays", due), ("estimatedMinutes", minutes)):
            if value != int(value) or (column != "deadlineInDays" and value < 1) or value < 0:
                raise _fail(path, line, column, "must be a whole number" + (" ≥ 1" if column != "deadlineInDays" else " ≥ 0"))
        start = _time(path, line, row, "plannedStart", required=False)
        end = _time(path, line, row, "plannedEnd", required=False)
        if (start is None) != (end is None) or (start and end <= start):
            raise _fail(path, line, "plannedEnd", "plannedStart and plannedEnd go together, end after start")
        delegable = row.get("delegable", "").lower()
        if delegable not in ("", "true", "false"):
            raise _fail(path, line, "delegable", "must be true or false")
        category = (row.get("category") or "").strip().lower() or None
        if category is not None and category not in engine_config.TASK_CATEGORIES:
            raise _fail(path, line, "category", f"must be empty or one of: {', '.join(engine_config.TASK_CATEGORIES)}")
        tasks.append(PlannedTask(
            persona_id=pid, day=int(day), task_id=task_id, title=row["title"], type=row["type"],
            priority=row["priority"], estimated_minutes=int(minutes), deadline_in_days=int(due),
            deadline_time=_time(path, line, row, "deadlineTime", required=False) or "23:59",
            planned_start=start, planned_end=end, delegable=delegable == "true",
            category=category or infer_category(row["title"]),
        ))
    return tasks


# --- task category from the title (PROPOSED rule, 16 Oct 2026) ---------------------------------

# Used only when the tasks file has no `category` value. Checked in this order; the first match
# wins; no match → None (meetings, planning, admin). Matching is on lower-case words.
CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("reading", (r"\bread\b", r"\bre-read\b", r"\breading\b", r"\bskim\b", r"search and shortlist", r"collect sources",
                 r"find sources")),
    ("revision", (r"\brevision\b", r"notes review", r"definitions review", r"feedback review", r"flashcards",
                  r"past paper", r"past lecture slides", r"\brecap\b", r"summary sheet")),
    ("coding", (r"lab sheet", r"\bcode\b", r"lab environment", r"practice lab", r"web feature", r"portfolio site")),
    ("writing", (r"assignment", r"\bwrit", r"\boutline\b", r"proofread", r"references", r"synthesis", r"\bslides\b",
                 r"speaker notes", r"\bdraft\b", r"lit review", r"\bnotes for\b")),
)


def infer_category(title: str) -> str | None:
    import re

    text = title.lower()
    for category, patterns in CATEGORY_RULES:
        if any(re.search(p, text) for p in patterns):
            return category
    return None


# --- schedule (one row per block of a persona's day) ------------------------------------------

SCHEDULE_KINDS = ("sleep", "routine", "bus", "office", "campus", "family", "tutor", "fixed", "study_window")
# 'study_window' (the data's name) = free time for tasks of any kind, not only study.
# Free-time windows may overlap these (tasks on the bus or train); every other kind wins
# over a window (e.g. a quiz or dinner inside a window stays protected).
TRAVEL_KINDS = ("bus",)
OUTSIDE_WINDOWS_LABEL = "Outside free time"
DAY_END = 24 * 60


@dataclass(frozen=True)
class ScheduleBlock:
    kind: str
    label: str
    start: int  # minutes after midnight
    end: int  # minutes after midnight; 1440 = 24:00


Schedule = dict[tuple[str, int], list[ScheduleBlock]]


def _minutes(path: Path, line: int, row: dict, column: str, allow_24: bool = False) -> int:
    text = row.get(column, "")
    if allow_24 and text == "24:00":
        return DAY_END
    if not is_time(text):
        raise _fail(path, line, column, f"'{text}' is not a time HH:MM" + (" (or 24:00)" if allow_24 else ""))
    return int(text[:2]) * 60 + int(text[3:])


def load_schedule(path: str | Path, personas: dict[str, Persona]) -> Schedule:
    path = Path(path)
    schedule: Schedule = defaultdict(list)
    for line, row in _rows(path):
        pid = row.get("personaId", "")
        if pid not in personas:
            raise _fail(path, line, "personaId", f"'{pid}' is not in the personas file")
        day = _number(path, line, row, "day", 0)
        if day != int(day) or day < 1:
            raise _fail(path, line, "day", "must be a whole number >= 1")
        if row.get("date") != day_to_date(int(day)):
            raise _fail(path, line, "date", f"'{row.get('date')}' does not match day {int(day)} ({day_to_date(int(day))})")
        if row.get("kind") not in SCHEDULE_KINDS:
            raise _fail(path, line, "kind", f"must be one of: {', '.join(SCHEDULE_KINDS)}")
        if not row.get("label"):
            raise _fail(path, line, "label", "is required")
        start = _minutes(path, line, row, "start")
        end = _minutes(path, line, row, "end", allow_24=True)
        if end <= start:
            raise _fail(path, line, "end", "must be after start (a block crossing midnight is split into two days)")
        schedule[(pid, int(day))].append(ScheduleBlock(row["kind"], row["label"], start, end))
    return dict(schedule)


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def study_windows(blocks: list[ScheduleBlock]) -> list[ScheduleBlock]:
    return sorted((b for b in blocks if b.kind == "study_window"), key=lambda b: b.start)


def free_minutes(blocks: list[ScheduleBlock]) -> list[bool]:
    """Per minute of the day: True when the student is free for tasks (inside a
    free-time window and not inside a non-travel block)."""
    free = [False] * (DAY_END + 1)
    for w in study_windows(blocks):
        for m in range(w.start, w.end):
            free[m] = True
    for b in blocks:
        if b.kind not in ("study_window", *TRAVEL_KINDS):
            for m in range(b.start, b.end):
                free[m] = False
    return free


def day_frame(blocks: list[ScheduleBlock]) -> tuple[dict[str, str], list[dict[str, str]]] | None:
    """Work hours and protected blocks for one scheduled day, or None without a free-time window.

    workHours = first window start to last window end. Protected blocks = every other
    block inside that span plus the gaps between windows; a travel block gives way to a
    window it overlaps (tasks on the bus), any other kind (quiz, dinner, work, campus,
    family, tutoring) stays protected.
    """
    windows = study_windows(blocks)
    if not windows:
        return None
    lo, hi = windows[0].start, max(w.end for w in windows)
    free = free_minutes(blocks)
    labels: list[str | None] = [None] * (DAY_END + 1)
    for m in range(lo, hi):
        if not free[m]:
            labels[m] = OUTSIDE_WINDOWS_LABEL
    for b in blocks:  # name a protected minute after the block that takes it
        if b.kind == "study_window":
            continue
        for m in range(max(b.start, lo), min(b.end, hi)):
            if not free[m]:
                labels[m] = b.label
    protected: list[dict[str, str]] = []
    m = lo
    while m < hi:
        if labels[m] is None:
            m += 1
            continue
        start, label = m, labels[m]
        while m < hi and labels[m] == label:
            m += 1
        protected.append({"id": f"s{len(protected) + 1}", "label": label, "start": _hhmm(start), "end": _hhmm(m)})
    end = _hhmm(hi) if hi < DAY_END else "23:59"
    return {"start": _hhmm(lo), "end": end}, protected


def night_shift_days(schedule: Schedule, persona_id: str) -> set[int]:
    """Days that begin with work continuing from the night before (an office block from 00:00)."""
    return {day for (pid, day), blocks in schedule.items()
            if pid == persona_id and any(b.kind == "office" and b.start == 0 for b in blocks)}
