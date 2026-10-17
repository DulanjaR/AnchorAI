"""Rearranger in the API (17 Oct 2026): where do the tasks an MVD moved off today go, and
how are effort tasks spread? The engine (engine/rearrange.py) proposes; nothing changes until
the student has chosen an option for every task that needs a decision and then accepts,
edits or rejects the whole proposal (logged like an MVD decision, for Model 2).

  build_input  the student's next 7 days: study windows = free hours split by the routine
               (each piece has a location; outside the routine: Home), fixed = protected
               blocks, planned = tasks (and effort sessions) already on those days; moved =
               the day's accepted Move tasks with the Model 1 corrected duration; effort tasks
  create / choose / decide   the proposal's life cycle
"""
from datetime import date as Date
from datetime import timedelta
from typing import Any, Literal

from components.c1_disruption.app.api.errors import bad_request, conflict, unprocessable
from components.c1_disruption.app.data.repository import Record
from components.c1_disruption.app.services.clock import iso_utc
from components.c1_disruption.app.services.mvd_service import Deps
from components.c1_disruption.app.services.owned import load_owned
from components.c1_disruption.app.services.planning import reward
from components.c1_disruption.engine import config
from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.rearrange import rearrange
from components.c1_disruption.engine.time import to_minutes

Action = Literal["accept", "edit", "reject"]
DEFAULT_LOCATION = "Home"


def _add(day: str, n: int) -> str:
    return (Date.fromisoformat(day) + timedelta(days=n)).isoformat()


def _hhmm(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


def windows(settings: Record) -> list[dict[str, Any]]:
    """Free hours split by the routine: [{start, end, location}]."""
    start, end = to_minutes(settings["workStart"]), to_minutes(settings["workEnd"])
    marks = sorted((max(start, to_minutes(r["start"])), min(end, to_minutes(r["end"])), r["location"])
                   for r in settings.get("routine") or [])
    out, cursor = [], start
    for s, e, loc in marks:
        if e <= s or e <= cursor:
            continue
        if s > cursor:
            out.append({"start": _hhmm(cursor), "end": _hhmm(s), "location": DEFAULT_LOCATION})
        out.append({"start": _hhmm(max(s, cursor)), "end": _hhmm(e), "location": loc})
        cursor = e
    if cursor < end:
        out.append({"start": _hhmm(cursor), "end": _hhmm(end), "location": DEFAULT_LOCATION})
    return out


def _corrected_minutes(store: Any, user_id: str, task: Record) -> tuple[int, str]:
    """Model 1's corrected duration from the MVD that moved the task (the estimate when the
    gate was closed or no model ran)."""
    mvd = store.get("mvds", task["mvdId"]) if task.get("mvdId") else None
    for log in (mvd or {}).get("taskLog") or []:
        if log["taskId"] == task["id"]:
            return round(log["correctedHours"] * 60), log["correctionSource"]
    return round(task["estimatedHours"] * 60), "estimate"


def build_input(store: Any, user_id: str, day: str) -> dict[str, Any]:
    settings = store.get("users", user_id)
    if settings is None:
        raise conflict("Set your free hours first", "NO_SETTINGS")
    tasks = [t for t in store.list("tasks", {"userId": user_id}) if t["status"] != "done"]
    fixed = [{"label": b["label"], "start": b["start"], "end": b["end"]}
             for b in store.list("protectedBlocks", {"userId": user_id})]
    days = []
    for n in range(1, config.REARRANGE_HORIZON_DAYS + 1):
        d = _add(day, n)
        planned = []
        for t in tasks:
            if t.get("plannedDate") == d and t.get("plannedStart") and not t.get("sessions"):
                planned.append({"id": t["id"], "title": t["title"], "type": t["type"], "priority": t["priority"],
                                "deadline": t["deadline"], "start": t["plannedStart"], "end": t["plannedEnd"]})
            for s in t.get("sessions") or []:
                if s["date"] == d and not s.get("done"):
                    planned.append({"id": f"{t['id']}@{d}@{s['start']}", "title": t["title"], "type": t["type"],
                                    "priority": t["priority"], "deadline": t["deadline"], "start": s["start"], "end": s["end"]})
        days.append({"date": d, "windows": windows(settings), "fixed": fixed, "planned": planned})
    moved, effort = [], []
    for t in tasks:
        if t.get("totalEffortMinutes"):
            if t["deadline"][:10] > day:
                effort.append({"id": t["id"], "title": t["title"], "type": t["type"], "priority": t["priority"],
                               "deadline": t["deadline"], "totalEffortMinutes": t["totalEffortMinutes"],
                               "actualMinutesDone": t.get("actualMinutesDone") or 0, "minSession": t.get("minSession"),
                               "maxSession": t.get("maxSession"), "splittable": True, "location": t.get("location"),
                               "sessions": t.get("sessions") or []})
            continue
        if t.get("plannedDate") == day and t.get("mvdTag") == "Move" and not t.get("rearrangedBy"):
            minutes, source = _corrected_minutes(store, user_id, t)
            moved.append({"id": t["id"], "title": t["title"], "type": t["type"], "priority": t["priority"],
                           "deadline": t["deadline"], "durationMinutes": minutes, "durationSource": source,
                           "splittable": t.get("splittable"), "delegable": t.get("delegable", False),
                           "location": t.get("location"), "minSession": t.get("minSession"),
                           "maxSession": t.get("maxSession")})
    return {"today": day, "from": f"{_add(day, 1)}T00:00", "horizonDays": config.REARRANGE_HORIZON_DAYS,
            "days": days, "moved": moved, "effort": effort}


def create(deps: Deps, user_id: str, day: str) -> Record:
    data = build_input(deps.store, user_id, day)
    try:
        result = rearrange(data)
    except EngineError as exc:
        raise unprocessable(str(exc)) from exc
    return deps.store.create("rearrangements", {
        "userId": user_id, "date": day, "status": "proposed", "input": data, "result": result, "choices": {},
        "createdAt": iso_utc(deps.clock.now()), "decidedAt": None,
    })


def choose(deps: Deps, user_id: str, rid: str, task_id: str, option: str) -> Record:
    rec = load_owned(deps.store, "rearrangements", rid, user_id, "Rearrangement")
    if rec["status"] != "proposed":
        raise conflict(f"This rearrangement is already {rec['status']}")
    decision = next((d for d in rec["result"]["needsDecision"] if d["taskId"] == task_id), None)
    if decision is None:
        raise bad_request(f"Task '{task_id}' does not need a decision here")
    chosen = next(o for o in decision["options"] if o["code"] == option)
    if not chosen["available"]:
        raise bad_request(f"Option {option} is not available: {chosen['reason']}")
    return deps.store.update("rearrangements", rec["id"], {"choices": {**rec["choices"], task_id: option}})


def _apply(store: Any, user_id: str, rec: Record, placements: list[dict[str, Any]], changes: list[dict[str, Any]]) -> None:
    """Writes placements (moved tasks, effort sessions) and the chosen options' changes."""
    by_task: dict[str, list[dict[str, Any]]] = {}
    for p in placements:
        by_task.setdefault(p["taskId"], []).append(p)
    for c in changes:
        if c["action"] == "place":
            by_task.setdefault(c["taskId"], []).append(c)
    effort_ids = {e["id"] for e in rec["input"]["effort"]}
    reasons = {d["taskId"]: next(o["reason"] for o in d["options"] if o["code"] == rec["choices"].get(d["taskId"]))
               for d in rec["result"]["needsDecision"] if d["taskId"] in rec["choices"]}
    for task_id, places in by_task.items():
        task = store.get("tasks", task_id)
        sessions = [{"date": p["date"], "start": p["start"], "end": p["end"],
                     "minutes": to_minutes(p["end"]) - to_minutes(p["start"]), "done": False} for p in places]
        # Why it is there (shown in the app): the rearranger's reason, the chosen option's, or "edited".
        reason = (reasons.get(task_id) or ("You chose this time yourself." if places[0].get("edited") else None)
                  or places[0].get("reason"))
        store.update("tasks", task_id, {"rearrangeReason": reason})
        if task_id in effort_ids:
            keep = [s for s in task.get("sessions") or [] if s.get("done") or s["date"] < rec["input"]["from"][:10]]
            store.update("tasks", task_id, {"sessions": keep + sessions})
        elif len(sessions) == 1:
            s = sessions[0]
            store.update("tasks", task_id, {"plannedDate": s["date"], "plannedStart": s["start"], "plannedEnd": s["end"],
                                            "rearrangedFrom": rec["date"], "rearrangedBy": rec["id"], "sessions": None})
        else:
            first = sessions[0]
            store.update("tasks", task_id, {"plannedDate": first["date"], "plannedStart": first["start"],
                                            "plannedEnd": first["end"], "rearrangedFrom": rec["date"],
                                            "rearrangedBy": rec["id"], "sessions": sessions})
    for c in changes:
        tid = c["taskId"]
        if c["action"] in ("move", "shorten") and "@" in tid:  # a session of another task
            owner, day, start = tid.split("@")
            task = store.get("tasks", owner)
            sessions = [dict(s) for s in task["sessions"]]
            for s in sessions:
                if s["date"] == day and s["start"] == start:
                    s.update(date=c["date"], start=c["start"], end=c["end"],
                             minutes=to_minutes(c["end"]) - to_minutes(c["start"]))
            store.update("tasks", owner, {"sessions": sessions})
        elif c["action"] == "move":
            store.update("tasks", tid, {"plannedDate": c["date"], "plannedStart": c["start"], "plannedEnd": c["end"],
                                        "movedBy": rec["id"]})
        elif c["action"] == "shorten":
            task = store.get("tasks", tid)
            store.update("tasks", tid, {"plannedEnd": c["end"], "shortenedBy": c["minutesCut"],
                                        "estimatedHours": round(task["estimatedHours"] - c["minutesCut"] / 60, 4)})
        elif c["action"] == "delegate":
            store.update("tasks", tid, {"mvdTag": "Delegate", "rearrangedBy": rec["id"]})
        elif c["action"] == "needsSlot":
            store.update("tasks", tid, {"needsSlot": True, "deadlineRisk": True,
                                        "shortfallMinutes": c["shortfallMinutes"], "rearrangedBy": rec["id"]})


def decide(deps: Deps, user_id: str, rid: str, action: Action, changes: list[Any] | None = None,
           reason: str | None = None) -> Record:
    store = deps.store
    rec = load_owned(store, "rearrangements", rid, user_id, "Rearrangement")
    if rec["status"] != "proposed":
        raise conflict(f"This rearrangement is already {rec['status']}; it can be decided only once")
    result = rec["result"]
    placements = [dict(p) for p in result["placements"]]
    edits = []
    if action in ("accept", "edit"):
        missing = [d["taskId"] for d in result["needsDecision"] if d["taskId"] not in rec["choices"]]
        if missing:
            raise conflict(f"Choose an option for: {', '.join(missing)}", "CHOICE_NEEDED")
    if action == "edit":
        blocks = store.list("protectedBlocks", {"userId": user_id})
        for ch in changes or []:
            ch = ch.model_dump() if hasattr(ch, "model_dump") else dict(ch)
            s, e = to_minutes(ch["start"]), to_minutes(ch["end"])
            if e <= s:
                raise bad_request(f"Task '{ch['taskId']}': 'end' must be after 'start'")
            hit = next((b["label"] for b in blocks if s < to_minutes(b["end"]) and to_minutes(b["start"]) < e), None)
            if hit:
                raise bad_request(f"Task '{ch['taskId']}' overlaps the protected block '{hit}'", "PROTECTED_BLOCK_OVERLAP")
            before = [p for p in placements if p["taskId"] == ch["taskId"]]
            if not before:
                raise bad_request(f"Task '{ch['taskId']}' is not placed in this rearrangement")
            placements = [p for p in placements if p["taskId"] != ch["taskId"]]
            placements.append({"taskId": ch["taskId"], "date": ch["date"], "start": ch["start"], "end": ch["end"],
                               "edited": True})
            edits.append({"taskId": ch["taskId"], "before": [{k: p[k] for k in ("date", "start", "end")} for p in before],
                          "after": {k: ch[k] for k in ("date", "start", "end")}})
    chosen_changes = []
    for d in result["needsDecision"]:
        code = rec["choices"].get(d["taskId"])
        if code:
            chosen_changes += next(o for o in d["options"] if o["code"] == code)["changes"]
    if action != "reject":
        _apply(store, user_id, rec, placements, chosen_changes)
    total = len({p["taskId"] for p in result["placements"]}) + len(result["needsDecision"])
    value = reward(action, len(edits), total)
    at = iso_utc(deps.clock.now())
    store.create("feedback", {
        "userId": user_id, "kind": "rearrange", "rearrangementId": rec["id"], "action": action, "edits": edits or None,
        "choices": rec["choices"], "reason": reason if action == "reject" else None, "at": at, "reward": value,
        "totalTasks": total,
    })
    status = {"accept": "accepted", "edit": "edited", "reject": "rejected"}[action]
    return store.update("rearrangements", rec["id"], {"status": status, "decidedAt": at,
                                                      "finalPlacements": placements if action != "reject" else None})
