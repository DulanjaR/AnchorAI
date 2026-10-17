"""PP1 web demo: a small page in front of the real C1 API.

    python -m components.c1_disruption.demo.web_demo            # then open http://127.0.0.1:8000
    python -m components.c1_disruption.demo.web_demo --port 8010 --no-browser

The student sets their week, adds tasks, reports disruptions and decides the plans. The
page calls the same API as the Flutter app will (docs/API.md).

Storage (17 Oct 2026): `--db` = a local SQLite file (default, in your home folder: data is kept
between runs), `supabase` (the team database: DATABASE_URL in the repo's .env, see README), or
`memory` (gone when the server stops). The clock runs in real time unless the page sets a
pretend time. For a local demo only: the page is given the API key so it can call the API.
"""
import argparse
import json
import threading
import webbrowser
from pathlib import Path

from datetime import datetime

from fastapi import Body, Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from components.c1_disruption.app.api.deps import require_user
from components.c1_disruption.app.api.validation import PRIORITIES
from components.c1_disruption.app.services.clock import COLOMBO, to_local
from components.c1_disruption.app.main import create_app
from components.c1_disruption.app.settings import c1_settings
from components.c1_disruption.engine import config
from shared.auth import require_api_key
from shared.config import settings as shared_settings

PAGE = Path(__file__).parent / "web" / "index.html"


def page_config() -> dict:
    return {
        "apiKey": shared_settings.api_key,
        "prefix": c1_settings.api_prefix,
        "taskTypes": list(config.TASK_TYPES),
        "categories": list(config.TASK_CATEGORIES),
        "locations": list(config.LOCATIONS),
        "priorities": list(PRIORITIES),
        "disruptionTypes": list(config.DISRUPTION_KINDS),
        "disruptionKinds": dict(config.DISRUPTION_KINDS),
    }


class DemoClock:
    """The demo's clock (local Colombo time). LIVE (real time) by default, so what you record is
    real; the page can set a PRETEND time (+5/+15/+30 min, or a time) to try the reminders and
    prompts, and go back to live."""

    def __init__(self) -> None:
        self.pretend: datetime | None = None

    @property
    def live(self) -> bool:
        return self.pretend is None

    def now(self) -> datetime:
        return self.pretend if self.pretend is not None else datetime.now(COLOMBO)

    def set(self, local: str) -> None:
        self.pretend = datetime.fromisoformat(local).replace(tzinfo=COLOMBO)

    def go_live(self) -> None:
        self.pretend = None


DEFAULT_DB = f"sqlite:///{Path.home() / 'anchor_c1_demo.sqlite3'}"


def store_for(db: str):
    """--db value → a store. 'supabase' = the team DATABASE_URL (repo .env)."""
    from components.c1_disruption.app.data.sql_store import make_store

    if db == "memory":
        return make_store(None)
    if db == "supabase":
        return make_store(shared_settings.database_url)
    return make_store(db)


def build_app(store=None) -> FastAPI:
    """The normal C1 app (given store, demo clock) plus the demo page, its clock and an export."""
    clock = DemoClock()
    app = create_app(store=store, clock=clock)

    @app.get("/demo/clock", include_in_schema=False)
    def get_clock() -> dict:
        date, time = to_local(clock.now())
        return {"now": f"{date}T{time}", "live": clock.live}

    @app.put("/demo/clock", include_in_schema=False)
    def set_clock(body: dict = Body(...)) -> dict:
        if body.get("live") is True:
            clock.go_live()
            return get_clock()
        try:
            clock.set(str(body["now"]))
        except (KeyError, ValueError):
            raise HTTPException(400, "Send {now: 'YYYY-MM-DDTHH:MM'} or {live: true}")
        return get_clock()

    @app.get("/demo/export", include_in_schema=False, dependencies=[Depends(require_api_key)])
    def export(user_id: str = Depends(require_user)) -> dict:
        """Everything stored for this student + Model 1 records + Model 2 decisions (JSON)."""
        from components.c1_disruption.metrics.records import export_user

        return export_user(app.state.deps.store, user_id)

    @app.get("/demo/info", include_in_schema=False)
    def info() -> dict:
        from components.c1_disruption.app.data.sql_store import SqlStore, safe_url

        s = app.state.deps.store
        return {"store": "memory" if not isinstance(s, SqlStore) else f"{s.kind}: {safe_url(s.url)}"}

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def demo_page() -> str:
        return PAGE.read_text(encoding="utf-8").replace("/*__CONFIG__*/{}", json.dumps(page_config()))

    return app


def main(argv: list[str] | None = None) -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--db", default=DEFAULT_DB,
                        help="sqlite:///path (default: a file in your home folder), 'supabase' (DATABASE_URL in .env), or 'memory'")
    args = parser.parse_args(argv)
    from components.c1_disruption.app.data.sql_store import SqlStore, safe_url

    store = store_for(args.db)
    print("C1 demo data:", "in memory (lost when the server stops)" if not isinstance(store, SqlStore) else safe_url(store.url))
    url = f"http://{args.host}:{args.port}/"
    print(f"C1 demo: open {url}  (API docs: {url}docs). Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run(build_app(store), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
