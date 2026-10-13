""""Now", as the API sees it. Injected into create_app so tests can fix the time.

All plan dates and times are Sri Lanka local time (Asia/Colombo). Sri Lanka has
been on UTC+05:30 all year since 2006 (no daylight saving), so a fixed offset is
exact and needs no time-zone database (Windows has none without tzdata).
"""
from datetime import datetime, timedelta, timezone
from typing import Protocol

COLOMBO = timezone(timedelta(hours=5, minutes=30), "Asia/Colombo")


class Clock(Protocol):
    def now(self) -> datetime:
        """The current instant (time-zone aware)."""


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FixedClock:
    """A fixed clock for tests, e.g. FixedClock('2026-10-07T09:00') = 09:00 Colombo time."""

    def __init__(self, local_date_time: str) -> None:
        self._instant = datetime.fromisoformat(local_date_time).replace(tzinfo=COLOMBO)

    def now(self) -> datetime:
        return self._instant


def to_local(instant: datetime) -> tuple[str, str]:
    """Instant → ('YYYY-MM-DD', 'HH:MM') in Colombo time."""
    local = instant.astimezone(COLOMBO)
    return local.strftime("%Y-%m-%d"), local.strftime("%H:%M")


def iso_utc(instant: datetime) -> str:
    """Same format as JavaScript's toISOString(): 2026-10-07T03:30:00.000Z."""
    utc = instant.astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{utc.microsecond // 1000:03d}Z"


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))
