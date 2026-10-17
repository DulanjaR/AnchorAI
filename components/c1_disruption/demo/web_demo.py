"""PP1 web demo: a small page in front of the real C1 API.

    python -m components.c1_disruption.demo.web_demo            # then open http://127.0.0.1:8000
    python -m components.c1_disruption.demo.web_demo --port 8010 --no-browser

The student sets their day, adds tasks, reports a disruption and sees the Minimum Viable
Day with every tag explained, then accepts or rejects it. The page calls the same API as
the Flutter app will (docs/API.md); data lives in memory and is gone when the server stops.
For a local demo only: the page is given the API key so it can call the API.
"""
import argparse
import json
import threading
import webbrowser
from pathlib import Path

from datetime import datetime

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from components.c1_disruption.app.api.validation import PRIORITIES
from components.c1_disruption.app.services.clock import COLOMBO, to_local
from components.c1_disruption.app.main import create_app
from components.c1_disruption.app.settings import c1_settings
from components.c1_disruption.engine import config
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
    """The demo's simulated clock (local Colombo time): the page jumps it +5/+15/+30 min or sets
    it, so "Started" times, MVDs and prompts follow the simulated time. Starts at the real time."""

    def __init__(self) -> None:
        self.instant = datetime.now(COLOMBO).replace(second=0, microsecond=0)

    def now(self) -> datetime:
        return self.instant

    def set(self, local: str) -> None:
        self.instant = datetime.fromisoformat(local).replace(tzinfo=COLOMBO)


def build_app() -> FastAPI:
    """The normal C1 app (in-memory store, simulated clock) plus the demo page and its clock."""
    clock = DemoClock()
    app = create_app(clock=clock)

    @app.get("/demo/clock", include_in_schema=False)
    def get_clock() -> dict:
        date, time = to_local(clock.now())
        return {"now": f"{date}T{time}"}

    @app.put("/demo/clock", include_in_schema=False)
    def set_clock(body: dict = Body(...)) -> dict:
        try:
            clock.set(str(body["now"]))
        except (KeyError, ValueError):
            raise HTTPException(400, "Send {now: 'YYYY-MM-DDTHH:MM'}")
        return get_clock()

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
    args = parser.parse_args(argv)
    url = f"http://{args.host}:{args.port}/"
    print(f"C1 demo: open {url}  (API docs: {url}docs). Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    uvicorn.run(build_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
