"""PP1 demo (Task 6): one disruption scenario end to end through the C1 API.

    python -m components.c1_disruption.demo.pp1_demo            # in-process, no server needed
    python -m components.c1_disruption.demo.pp1_demo --url http://127.0.0.1:8000

Story: SYNTHETIC persona P01 plans Monday 19 Oct 2026, a power cut hits at 09:00, P01
confirms it, C1 builds the Minimum Viable Day, explains every tag, and P01 accepts. The tasks
then carry the tags Components 3 (Keep) and 4 (Delegate) read.

Model 1 is on: it is trained on the SYNTHETIC persona history (sim/data/, seed 11, planted
drift: P01 runs over on Digital tasks), so P01 has enough history for the earned-trust gate
to open; the demo prints whether it is open. The day itself is hand-written for the demo.
Everything here is SYNTHETIC, not a research result.
"""
import argparse
import json
from typing import Any

import httpx

from components.c1_disruption.app.settings import c1_settings
from shared.config import settings as shared_settings

NOW = "2026-10-19T09:00"
DAY = "2026-10-19"
USER = "P01"  # SYNTHETIC persona with 30 days of history (sim/data/)
MODEL_SEED = 11
MODEL_TREES = 100

WORK_HOURS = {"workStart": "09:00", "workEnd": "17:00"}
BLOCKS = [{"label": "Lunch", "start": "12:30", "end": "13:30"}]
# The original plan: four tasks slotted, two more "if there is time" (no slot).
TASKS = [
    {"title": "Lab report (submit tonight)", "type": "Digital", "priority": "High", "estimatedHours": 2,
     "deadline": f"{DAY}T23:59", "plannedStart": "09:00", "plannedEnd": "11:00"},
    {"title": "Revise for Tuesday quiz", "type": "Analog", "priority": "High", "estimatedHours": 1.5,
     "deadline": "2026-10-20T09:00", "plannedStart": "11:00", "plannedEnd": "12:30"},
    {"title": "Maths problem sheet", "type": "Analog", "priority": "High", "estimatedHours": 2,
     "deadline": "2026-10-20T17:00", "plannedStart": "13:30", "plannedEnd": "15:30"},
    {"title": "Group slides", "type": "Digital", "priority": "Medium", "estimatedHours": 1.5, "delegable": True,
     "deadline": "2026-10-21T17:00", "plannedStart": "15:30", "plannedEnd": "17:00"},
    {"title": "Read chapter 5", "type": "Analog", "priority": "Medium", "estimatedHours": 1,
     "deadline": "2026-10-22T17:00"},
    {"title": "Online course video", "type": "Digital", "priority": "Medium", "estimatedHours": 2,
     "deadline": "2026-10-21T23:59"},
]
DISRUPTION = {"date": DAY, "type": "power_outage", "start": "09:00", "timeLostMinutes": 150, "severity": 3,
              "confirmed": True}


def train_model(n_estimators: int = MODEL_TREES):
    """Model 1 trained on the SYNTHETIC persona history (the notebook 01 data)."""
    from pathlib import Path

    from components.c1_disruption.ml.drift.data import clean
    from components.c1_disruption.ml.drift.model import DriftModel
    from components.c1_disruption.sim.generate import generate
    from components.c1_disruption.sim.personas import load_personas, load_schedule, load_tasks
    from components.c1_disruption.sim.profile import load_profile

    data = Path(__file__).resolve().parents[1] / "sim" / "data"
    personas = load_personas(str(data / "SYNTHETIC_personas.csv"), str(data / "SYNTHETIC_habits.csv"))
    tasks = load_tasks(str(data / "SYNTHETIC_tasks_planned.csv"), personas)
    schedule = load_schedule(str(data / "SYNTHETIC_schedule.csv"), personas)
    profile = load_profile(str(data / "SYNTHETIC_disruption_profile.csv"), personas)
    world = generate(personas, tasks, seed=MODEL_SEED, variant="planted", schedule=schedule, profile=profile)
    records = clean(world.records)
    return DriftModel(n_estimators=n_estimators).fit(records), records


class Api:
    """Sends the team API key and X-User-Id; in-process (TestClient) or to a running server."""

    def __init__(self, url: str | None, corrector: Any = None) -> None:
        self.headers = {"X-API-Key": shared_settings.api_key, "X-User-Id": USER}
        self.prefix = c1_settings.api_prefix
        self.store = None
        if url:
            self.client: Any = httpx.Client(base_url=url, timeout=30)
        else:
            from fastapi.testclient import TestClient

            from components.c1_disruption.app.data.memory_store import MemoryStore
            from components.c1_disruption.app.main import create_app
            from components.c1_disruption.app.services.clock import FixedClock

            self.store = MemoryStore()
            self.client = TestClient(create_app(store=self.store, clock=FixedClock(NOW), corrector=corrector))

    def __call__(self, method: str, path: str, body: Any = None) -> Any:
        response = self.client.request(method, self.prefix + path, headers=self.headers, json=body)
        if response.status_code >= 400:
            raise SystemExit(f"{method} {path} → {response.status_code}: {response.text}")
        return response.json()


def table(rows: list[list[str]], head: list[str]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(head, *rows)]
    line = lambda r: "  ".join(str(x).ljust(w) for x, w in zip(r, widths))
    return "\n".join([line(head), line(["-" * w for w in widths]), *map(line, rows)])


def run(url: str | None = None, out=print) -> dict[str, Any]:
    from components.c1_disruption.ml.drift.corrector import ModelCorrector

    model, records = train_model()
    trust = model.trust[USER]
    history = [r for r in records if r["studentId"] == USER]
    out(f"== 0. Model 1 for persona {USER} (SYNTHETIC history: {len(history)} finished tasks over "
        f"{len({r['date'] for r in history})} days) ==")
    out(f"Earned-trust gate for {USER}: {'OPEN' if trust.trusted else 'CLOSED'}. On {USER}'s {trust.n_recent} most "
        f"recent tasks the model was off by {trust.model_mae:.1f} min on average, {USER}'s own estimate by "
        f"{trust.b0_mae:.1f} min.")
    out("  → Model 1 corrects this student's durations." if trust.trusted
        else "  → Model 1 keeps this student's own estimates (drift 1.0).")
    if url:
        out("  (server mode: the server uses its own Model 1 setting, C1_DRIFT_MODEL_PATH; the gate shown is the local model's)")
    api = Api(url, corrector=ModelCorrector(model))
    out(f"\n== 1. {USER}'s normal day (Monday 19 Oct 2026) ==")
    api("PUT", "/me/settings", WORK_HOURS)
    for block in BLOCKS:
        api("POST", "/protected-blocks", block)
    titles = {}
    for task in TASKS:
        created = api("POST", "/tasks", {**task, "plannedDate": DAY})
        titles[created["id"]] = created["title"]
    out(table([[f"{t['plannedStart']}–{t['plannedEnd']}" if "plannedStart" in t else "if time", t["title"], t["type"], t["priority"],
                f"{t['estimatedHours']} h", t["deadline"].replace("T", " ")] for t in TASKS],
              ["planned", "task", "type", "priority", "length", "due"]))
    out(f"Protected: {', '.join(b['label'] + ' ' + b['start'] + '–' + b['end'] for b in BLOCKS)}")

    out("\n== 2. 09:00 power cut, 2 h 30 min lost; the student confirms it ==")
    report = api("POST", "/disruptions", DISRUPTION)
    out(f"disruption {report['id']}: {report['type']} {report['start']} for {report['timeLostMinutes']} min, "
        f"severity {report['severity']}")

    out("\n== 3. Minimum Viable Day (proposed, nothing changes until the student decides) ==")
    mvd = api("POST", f"/disruptions/{report['id']}/mvd", {"planFrom": "09:00"})
    if mvd.get("taskLog"):
        out(f"Durations used by the planner (Model 1, gate {'open' if trust.trusted else 'closed'}):")
        out(table([[titles.get(log["taskId"], log["taskId"]), f"{log['estimatedHours']} h", f"{log['correctedHours']:.2f} h",
                    f"{log['correctedLowHours']:.2f}–{log['correctedHighHours']:.2f} h", log["correctionSource"]]
                   for log in mvd["taskLog"]], ["task", "estimate", "used", "range (q10–q90)", "source"]))
        out("")
    rows = []
    for t in mvd["plan"]["tasks"]:
        slot = f"{t['start']}–{t['end']}" if t.get("start") else "—"
        risk = " ⚠ deadline" if t.get("deadlineRisk") else ""
        rows.append([t["tag"] + risk, slot, titles.get(t["id"], t["id"]), t["reason"]])
    out(table(rows, ["tag", "slot", "task", "reason"]))
    out("\nWhy (shown to the student for every tag):")
    for t in mvd["plan"]["tasks"]:
        out(f"- {titles.get(t['id'], t['id'])}: {t['explanation']}")
    for w in mvd["plan"].get("warnings") or []:
        out(f"- warning {w['code']}: {w['message']}")

    out("\n== 4. The student accepts ==")
    api("POST", f"/mvds/{mvd['id']}/accept")
    tasks = api("GET", f"/tasks?date={DAY}")
    out(table([[t["title"], t.get("mvdTag") or "", f"{t.get('mvdStart') or ''}–{t.get('mvdEnd') or ''}".strip("–")]
               for t in tasks], ["task", "mvdTag", "new slot"]))
    keep = [t["title"] for t in tasks if t.get("mvdTag") == "Keep"]
    delegate = [t["title"] for t in tasks if t.get("mvdTag") == "Delegate"]
    out(f"Component 3 reads Keep: {keep}")
    out(f"Component 4 reads Delegate: {delegate}")
    feedback = api.store.list("feedback") if api.store is not None else []
    if feedback:
        out(f"Logged for Model 2: decision '{feedback[0]['action']}', reward {feedback[0]['reward']}")
    return {"mvd": mvd, "tasks": tasks, "feedback": feedback, "trust": trust}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", help="a running C1 server, e.g. http://127.0.0.1:8000 (default: in-process)")
    parser.add_argument("--json", action="store_true", help="also print the raw MVD as JSON")
    args = parser.parse_args(argv)
    result = run(args.url)
    if args.json:
        print(json.dumps(result["mvd"], indent=2))


if __name__ == "__main__":
    main()
