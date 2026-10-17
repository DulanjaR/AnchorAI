"""Rearranger in the API (17 Oct 2026): propose → choose → accept / edit / reject."""
from components.c1_disruption.app.services.rearrange_service import windows
from components.c1_disruption.tests.api.client import setup

TODAY = "2026-11-02"  # Monday
ROUTINE = [{"label": "Bus", "start": "08:00", "end": "08:45", "location": "Commute"},
           {"label": "Lectures", "start": "09:00", "end": "16:00", "location": "Campus"}]


def day_with_moved_task(hours=("08:00", "22:00"), deadline="2026-11-07T23:59", minutes=60, **extra):
    """A real MVD that moves one low-urgency task off today; accepted."""
    ctx = setup(f"{TODAY}T09:00")
    ctx.call("PUT", "/api/me/settings", body={"workStart": hours[0], "workEnd": hours[1], "routine": ROUTINE})
    task = ctx.call("POST", "/api/tasks", body={"title": "Read survey paper", "type": "Digital", "priority": "Low",
                                                 "estimatedHours": minutes / 60, "deadline": deadline,
                                                 "plannedDate": TODAY, **extra}).json()
    report = ctx.call("POST", "/api/disruptions", body={"date": TODAY, "type": "transport_delay", "start": "09:00",
                                                         "timeLostMinutes": 30, "severity": 2, "confirmed": True}).json()
    mvd = ctx.call("POST", f"/api/disruptions/{report['id']}/mvd", body={"planFrom": "09:00"}).json()
    assert mvd["plan"]["tasks"][0]["tag"] == "Move"
    ctx.call("POST", f"/api/mvds/{mvd['id']}/accept")
    return ctx, task


def test_routine_splits_the_free_hours_into_located_windows():
    assert windows({"workStart": "08:00", "workEnd": "22:00", "routine": ROUTINE}) == [
        {"start": "08:00", "end": "08:45", "location": "Commute"}, {"start": "08:45", "end": "09:00", "location": "Home"},
        {"start": "09:00", "end": "16:00", "location": "Campus"}, {"start": "16:00", "end": "22:00", "location": "Home"}]
    assert windows({"workStart": "09:00", "workEnd": "17:00"}) == [{"start": "09:00", "end": "17:00", "location": "Home"}]


def test_settings_routine_is_optional_and_kept_when_not_sent():
    ctx = setup()
    plain = ctx.call("PUT", "/api/me/settings", body={"workStart": "09:00", "workEnd": "17:00"}).json()
    assert "routine" not in plain  # earlier clients see the same object
    ctx.call("PUT", "/api/me/settings", body={"workStart": "08:00", "workEnd": "22:00", "routine": ROUTINE})
    kept = ctx.call("PUT", "/api/me/settings", body={"workStart": "08:00", "workEnd": "21:00"}).json()
    assert kept["routine"] == ROUTINE
    bad = ctx.call("PUT", "/api/me/settings", body={"workStart": "08:00", "workEnd": "21:00",
                                                    "routine": [{**ROUTINE[0], "location": "Moon"}]})
    assert bad.status_code == 400 and "location" in bad.json()["error"]["message"]


def test_new_task_fields_are_optional_and_checked():
    ctx = setup()
    base = {"title": "Essay", "type": "Analog", "priority": "Medium", "estimatedHours": 7,
            "deadline": "2026-10-14T23:59", "plannedDate": "2026-10-07"}
    plain = ctx.call("POST", "/api/tasks", body=base).json()
    assert not {"location", "totalEffortMinutes", "minSession", "maxSession", "splittable"} & set(plain)
    effort = ctx.call("POST", "/api/tasks", body={**base, "location": "Campus", "totalEffortMinutes": 420,
                                                   "minSession": 30, "maxSession": 90, "splittable": True}).json()
    assert (effort["location"], effort["totalEffortMinutes"], effort["maxSession"]) == ("Campus", 420, 90)
    assert ctx.call("POST", "/api/tasks", body={**base, "minSession": 90, "maxSession": 30}).status_code == 400
    assert ctx.call("POST", "/api/tasks", body={**base, "location": "Mars"}).status_code == 400


def test_moved_task_is_proposed_on_a_later_day_and_placed_only_after_accept():
    ctx, task = day_with_moved_task()
    rec = ctx.call("POST", "/api/rearrange", body={"date": TODAY}).json()
    (p,) = rec["result"]["placements"]
    # Tue: the commute takes only Analog tasks and 08:45–09:00 is too small → campus time 09:00–10:00.
    assert (p["taskId"], p["date"], p["start"], p["end"]) == (task["id"], "2026-11-03", "09:00", "10:00")
    assert p["reason"].startswith("Placed on Tue 3 Nov, 09:00–10:00")
    assert ctx.call("GET", f"/api/tasks/{task['id']}").json()["plannedDate"] == TODAY  # nothing changed yet
    done = ctx.call("POST", f"/api/rearrangements/{rec['id']}/accept").json()
    assert done["status"] == "accepted"
    moved = ctx.call("GET", f"/api/tasks/{task['id']}").json()
    assert (moved["plannedDate"], moved["plannedStart"], moved["rearrangedFrom"]) == ("2026-11-03", "09:00", TODAY)
    (fb,) = [f for f in ctx.store.list("feedback") if f.get("kind") == "rearrange"]
    assert (fb["action"], fb["reward"]) == ("accept", 1.0)
    # Already rearranged: a second proposal has nothing to move.
    assert ctx.call("POST", "/api/rearrange", body={"date": TODAY}).json()["result"]["placements"] == []


def test_needs_decision_waits_for_a_choice():
    ctx, task = day_with_moved_task(hours=("20:00", "20:30"), deadline="2026-11-04T23:59", minutes=120)
    rec = ctx.call("POST", "/api/rearrange", body={"date": TODAY}).json()
    (d,) = rec["result"]["needsDecision"]
    assert d["shortfallMinutes"] == 60 and [o["available"] for o in d["options"]] == [False, False, True, False, True]
    assert ctx.call("POST", f"/api/rearrangements/{rec['id']}/accept").json()["error"]["code"] == "CHOICE_NEEDED"
    bad = ctx.call("POST", f"/api/rearrangements/{rec['id']}/choose", body={"taskId": task["id"], "option": "A"})
    assert bad.status_code == 400 and "not available" in bad.json()["error"]["message"]
    ctx.call("POST", f"/api/rearrangements/{rec['id']}/choose", body={"taskId": task["id"], "option": "E"})
    ctx.call("POST", f"/api/rearrangements/{rec['id']}/accept")
    t = ctx.call("GET", f"/api/tasks/{task['id']}").json()
    assert (t["needsSlot"], t["deadlineRisk"], t["shortfallMinutes"]) == (True, True, 60)


def test_option_c_splits_the_shortened_task_into_sessions():
    ctx, task = day_with_moved_task(hours=("20:00", "20:30"), deadline="2026-11-04T23:59", minutes=120)
    rec = ctx.call("POST", "/api/rearrange", body={"date": TODAY}).json()
    ctx.call("POST", f"/api/rearrangements/{rec['id']}/choose", body={"taskId": task["id"], "option": "C"})
    ctx.call("POST", f"/api/rearrangements/{rec['id']}/accept")
    t = ctx.call("GET", f"/api/tasks/{task['id']}").json()
    assert [(s["date"], s["start"], s["end"]) for s in t["sessions"]] == [("2026-11-03", "20:00", "20:30"),
                                                                       ("2026-11-04", "20:00", "20:30")]


def test_edit_and_reject():
    ctx, task = day_with_moved_task()
    rec = ctx.call("POST", "/api/rearrange", body={"date": TODAY}).json()
    ctx.call("POST", "/api/protected-blocks", body={"label": "Gym", "start": "18:00", "end": "19:00"})
    clash = ctx.call("POST", f"/api/rearrangements/{rec['id']}/edit",
                     body={"changes": [{"taskId": task["id"], "date": "2026-11-04", "start": "18:30", "end": "19:30"}]})
    assert clash.json()["error"]["code"] == "PROTECTED_BLOCK_OVERLAP"
    ok = ctx.call("POST", f"/api/rearrangements/{rec['id']}/edit",
                  body={"changes": [{"taskId": task["id"], "date": "2026-11-04", "start": "19:00", "end": "20:00"}]}).json()
    assert ok["status"] == "edited"
    assert ctx.call("GET", f"/api/tasks/{task['id']}").json()["plannedDate"] == "2026-11-04"
    ctx2, task2 = day_with_moved_task()
    rec2 = ctx2.call("POST", "/api/rearrange", body={"date": TODAY}).json()
    assert ctx2.call("POST", f"/api/rearrangements/{rec2['id']}/reject", body={"reason": "busy"}).json()["status"] == "rejected"
    assert ctx2.call("GET", f"/api/tasks/{task2['id']}").json()["plannedDate"] == TODAY  # nothing changed


def test_effort_task_sessions_and_session_done():
    ctx = setup(f"{TODAY}T09:00")
    ctx.call("PUT", "/api/me/settings", body={"workStart": "19:00", "workEnd": "21:00"})
    task = ctx.call("POST", "/api/tasks", body={"title": "Project report", "type": "Digital", "priority": "Medium",
                                                 "estimatedHours": 7, "deadline": "2026-11-10T23:59", "plannedDate": TODAY,
                                                 "totalEffortMinutes": 420}).json()
    rec = ctx.call("POST", "/api/rearrange", body={"date": TODAY}).json()
    assert [p["minutes"] for p in rec["result"]["placements"]] == [60] * 7
    ctx.call("POST", f"/api/rearrangements/{rec['id']}/accept")
    t = ctx.call("GET", f"/api/tasks/{task['id']}").json()
    assert len(t["sessions"]) == 7 and t["sessions"][0] == {"date": "2026-11-03", "start": "19:00", "end": "20:00",
                                                           "minutes": 60, "done": False}
    done = ctx.call("POST", f"/api/tasks/{task['id']}/sessions/done", body={"date": "2026-11-03"}).json()
    assert done["actualMinutesDone"] == 60 and done["sessions"][0]["done"] is True
