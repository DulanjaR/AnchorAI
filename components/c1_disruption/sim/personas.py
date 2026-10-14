"""Layer A: load and check the owner's persona and task lists (format: sim/README.md)."""
import csv
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from components.c1_disruption.app.services.planning import STRATEGIES
from components.c1_disruption.engine import config as engine_config
from components.c1_disruption.ml.bandit.actions import ACTIONS
from components.c1_disruption.sim import settings
from components.c1_disruption.app.api.validation import is_time


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


def load_personas(path: str | Path) -> dict[str, Persona]:
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
    return personas


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
        tasks.append(PlannedTask(
            persona_id=pid, day=int(day), task_id=task_id, title=row["title"], type=row["type"],
            priority=row["priority"], estimated_minutes=int(minutes), deadline_in_days=int(due),
            deadline_time=_time(path, line, row, "deadlineTime", required=False) or "23:59",
            planned_start=start, planned_end=end, delegable=delegable == "true",
        ))
    return tasks
