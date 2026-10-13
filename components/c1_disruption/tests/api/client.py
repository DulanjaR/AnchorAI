"""Test client for the C1 API: a fresh app with an in-memory store and a clock the
test can move, plus a small client that sends the team API key and X-User-Id."""
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi.testclient import TestClient

from components.c1_disruption.app.data.memory_store import MemoryStore
from components.c1_disruption.app.main import create_app
from components.c1_disruption.app.services.clock import FixedClock
from components.c1_disruption.app.settings import c1_settings
from shared.config import settings

API_KEY_HEADERS = {"X-API-Key": settings.api_key}
PREFIX = c1_settings.api_prefix


class MovableClock:
    def __init__(self, local_date_time: str) -> None:
        self.set(local_date_time)

    def set(self, local_date_time: str) -> None:
        self._clock = FixedClock(local_date_time)

    def now(self):
        return self._clock.now()


def api_path(path: str) -> str:
    """Paths in tests and api_cases.json use /api; the app serves the configured prefix."""
    return PREFIX + path[len("/api"):] if path.startswith("/api") else path


@dataclass
class Setup:
    client: TestClient
    store: MemoryStore
    clock: MovableClock

    def call(
        self,
        method: str,
        path: str,
        user: str | None = "u1",
        body: Any = None,
        raw: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        all_headers = {**API_KEY_HEADERS, **(headers or {})}
        if user is not None:
            all_headers["X-User-Id"] = user
        kwargs: dict[str, Any] = {"headers": all_headers}
        if raw is not None:
            kwargs["content"] = raw.encode("utf-8")
        elif body is not None:
            kwargs["json"] = body
        return self.client.request(method, api_path(path), **kwargs)


def setup(now: str = "2026-10-07T09:00") -> Setup:
    store = MemoryStore()
    clock = MovableClock(now)
    # raise_server_exceptions=False: a bug shows as a 500 response, as a client would see it.
    client = TestClient(create_app(store=store, clock=clock), raise_server_exceptions=False)
    return Setup(client, store, clock)
