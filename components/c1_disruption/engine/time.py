"""Time and interval helpers for the MVD engine. Pure functions only.

Within one planning day, a time of day is stored as minutes after midnight
(09:30 → 570). An interval is (start, end) in minutes, with start < end.
Whole-minute numbers make overlap checks exact (no floating-point time).
"""
import re
from datetime import date
from typing import Mapping, NamedTuple

from components.c1_disruption.engine.errors import EngineError

MINUTES_PER_HOUR = 60
MINUTES_PER_DAY = 24 * MINUTES_PER_HOUR

_TIME = re.compile(r"([0-9]{1,2}):([0-9]{2})")
_DATE = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")


class Interval(NamedTuple):
    start: int  # minutes after midnight
    end: int


def to_minutes(hhmm: str) -> int:
    """'HH:MM' → minutes after midnight."""
    match = _TIME.fullmatch(str(hhmm))
    if not match:
        raise EngineError(f"Invalid time '{hhmm}', expected HH:MM")
    hours, minutes = int(match[1]), int(match[2])
    if hours > 23 or minutes > 59:
        raise EngineError(f"Invalid time '{hhmm}', expected HH:MM")
    return hours * MINUTES_PER_HOUR + minutes


def to_hhmm(total_minutes: int) -> str:
    """Minutes after midnight → 'HH:MM' (1440 → '24:00', the end of the day)."""
    hours, minutes = divmod(total_minutes, MINUTES_PER_HOUR)
    return f"{hours:02d}:{minutes:02d}"


def parse_date(date_str: str) -> date:
    """'YYYY-MM-DD' → date. A date that does not exist (2026-02-30) is an error."""
    match = _DATE.fullmatch(str(date_str))
    if not match:
        raise EngineError(f"Invalid date '{date_str}', expected YYYY-MM-DD")
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        raise EngineError(f"Invalid date '{date_str}', expected YYYY-MM-DD") from None


def parse_date_time(date_time_str: str) -> int:
    """'YYYY-MM-DDTHH:MM' → minutes since a fixed epoch. A bare date = end of that day.

    Only used to order deadlines (tie-break), so the time zone does not matter.
    """
    date_part, _, time_part = str(date_time_str).partition("T")
    minutes = to_minutes(time_part[:5] if time_part else "23:59")
    return parse_date(date_part).toordinal() * MINUTES_PER_DAY + minutes


def calendar_days_between(plan_date: str, deadline: str) -> int:
    """Calendar days from the plan date to the deadline's date.

    Due today = 0, tomorrow = 1, overdue = negative. The time of day is ignored on
    purpose: "days until deadline" is the locked encoding for Deadline Proximity.
    """
    deadline_date = str(deadline).split("T")[0]
    return (parse_date(deadline_date) - parse_date(plan_date)).days


def overlaps(a: Interval, b: Interval) -> bool:
    """Touching intervals (one ends where the other starts) do NOT overlap."""
    return a.start < b.end and b.start < a.end


def subtract_interval(intervals: list[Interval], cut: Interval) -> list[Interval]:
    """Removes `cut` from every interval in the list.

    The result keeps the original order (sorted by start if the input was) and
    contains no empty intervals.
    """
    result: list[Interval] = []
    for iv in intervals:
        if not overlaps(iv, cut):
            result.append(iv)
            continue
        if iv.start < cut.start:
            result.append(Interval(iv.start, cut.start))
        if cut.end < iv.end:
            result.append(Interval(cut.end, iv.end))
    return result


def block_to_intervals(block: Mapping[str, str]) -> list[Interval]:
    """A protected block as intervals on the plan day.

    A block that crosses midnight (e.g. sleep 22:00–06:00) becomes two pieces:
    22:00–24:00 and 00:00–06:00.
    """
    start, end = to_minutes(block["start"]), to_minutes(block["end"])
    if start < end:
        return [Interval(start, end)]
    if start == end:
        return []
    pieces = [Interval(start, MINUTES_PER_DAY), Interval(0, end)]
    return [iv for iv in pieces if iv.start < iv.end]


def window_to_interval(disruption: Mapping[str, str]) -> Interval:
    """The disruption window as an interval on the plan day.

    A window that crosses midnight (e.g. power cut 20:00–02:00) is clipped at the
    end of the plan day → 20:00–24:00; the part after midnight belongs to
    tomorrow's plan (owner decision, 6 Oct 2026).
    """
    start, end = to_minutes(disruption["start"]), to_minutes(disruption["end"])
    return Interval(start, MINUTES_PER_DAY if end < start else end)


_TWO_DIGIT_TIME = re.compile(r"[0-9]{2}:[0-9]{2}")


def is_time(value: object) -> bool:
    """'HH:MM' with two-digit hours, a real time of day. (Used by the API checks and the
    simulation loaders; lives here so the simulation does not need the web layer.)"""
    if not isinstance(value, str) or not _TWO_DIGIT_TIME.fullmatch(value):
        return False
    try:
        to_minutes(value)
    except EngineError:
        return False
    return True
