"""The PP1 web demo (demo/web_demo.py): the page is served with its settings, and the calls
the page makes (sample day → disruption → MVD → accept) work on the same app."""
import json
import re

from fastapi.testclient import TestClient

from components.c1_disruption.demo import web_demo
from components.c1_disruption.engine import config
from shared.config import settings


def client() -> TestClient:
    return TestClient(web_demo.build_app())


def test_the_page_is_served_with_its_settings():
    page = client().get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "/*__CONFIG__*/" not in page.text
    cfg = json.loads(re.search(r"const CFG = (\{.*?\});", page.text).group(1))
    assert cfg["apiKey"] == settings.api_key
    assert cfg["taskTypes"] == list(config.TASK_TYPES)
    assert set(cfg["disruptionTypes"]) == set(config.DISRUPTION_KINDS)


def test_the_page_flow_works_on_the_demo_app():
    c = client()
    headers = {"X-API-Key": settings.api_key, "X-User-Id": "student-test"}
    call = lambda method, path, body=None: c.request(method, "/api" + path, headers=headers, json=body)
    assert call("PUT", "/me/settings", {"workStart": "09:00", "workEnd": "17:00"}).status_code == 200
    call("POST", "/protected-blocks", {"label": "Lunch", "start": "12:30", "end": "13:30"})
    day = "2026-10-19"
    for title, type_, priority, hours, deadline, slot in [
        ("Lab report", "Digital", "High", 2, f"{day}T23:59", ("09:00", "11:00")),
        ("Quiz", "Analog", "High", 1.5, "2026-10-20T09:00", ("11:00", "12:30")),
        ("Read", "Analog", "Medium", 1, "2026-10-22T17:00", None),
    ]:
        body = {"title": title, "type": type_, "priority": priority, "estimatedHours": hours, "deadline": deadline,
                "plannedDate": day, "delegable": False}
        if slot:
            body.update(plannedStart=slot[0], plannedEnd=slot[1])
        assert call("POST", "/tasks", body).status_code == 201
    report = call("POST", "/disruptions", {"date": day, "type": "power_outage", "start": "09:00",
                                            "timeLostMinutes": 150, "severity": 3, "confirmed": True}).json()
    mvd = call("POST", f"/disruptions/{report['id']}/mvd", {"planFrom": "09:00"}).json()
    # Fields the page reads.
    assert {"disruption", "horizon", "tasks", "protect", "freeMinutesLeft", "warnings"} <= set(mvd["plan"])
    assert all({"title", "tag", "start", "end", "reason", "explanation", "fi", "deadline"} <= set(t)
               for t in mvd["plan"]["tasks"])
    assert mvd["comparison"]["original"][0]["start"] == "09:00"
    accepted = call("POST", f"/mvds/{mvd['id']}/accept").json()
    assert accepted["status"] == "accepted"
    tasks = call("GET", f"/tasks?date={day}").json()
    assert all(t["mvdTag"] for t in tasks)


def test_demo_clock_can_be_set_and_drives_the_api():
    c = client()
    assert c.put("/demo/clock", json={"now": "2026-11-02T13:55"}).json() == {"now": "2026-11-02T13:55"}
    assert c.get("/demo/clock").json()["now"] == "2026-11-02T13:55"
    assert c.put("/demo/clock", json={"now": "not a time"}).status_code == 400
    headers = {"X-API-Key": settings.api_key, "X-User-Id": "s"}
    task = c.post("/api/tasks", headers=headers, json={"title": "T", "type": "Analog", "priority": "High", "estimatedHours": 1,
                                                       "deadline": "2026-11-02T23:59", "plannedDate": "2026-11-02"}).json()
    started = c.post(f"/api/tasks/{task['id']}/start", headers=headers).json()
    assert started["startedAt"] == "2026-11-02T08:25:00.000Z"  # 13:55 Colombo = 08:25 UTC: the simulated time


def test_page_config_has_the_new_lists():
    cfg = json.loads(re.search(r"const CFG = (\{.*?\});", client().get("/").text).group(1))
    assert cfg["locations"] == list(config.LOCATIONS) and cfg["categories"] == list(config.TASK_CATEGORIES)


def test_the_week_story_works_through_the_demo_app():
    """Sample-like day: power cut → MVD accepted → the rest of the week proposed → choose → accept."""
    c = client()
    headers = {"X-API-Key": settings.api_key, "X-User-Id": "week"}
    call = lambda m, p, b=None: c.request(m, "/api" + p, headers=headers, json=b).json()
    c.put("/demo/clock", json={"now": "2026-11-02T14:00"})
    call("PUT", "/me/settings", {"workStart": "17:00", "workEnd": "18:00"})
    tight = call("POST", "/tasks", {"title": "Report", "type": "Digital", "priority": "Medium", "estimatedHours": 2,
                                    "deadline": "2026-11-03T23:59", "plannedDate": "2026-11-02"})
    rep = call("POST", "/disruptions", {"date": "2026-11-02", "type": "power_outage", "start": "17:00",
                                        "timeLostMinutes": 60, "severity": 3, "confirmed": True})
    mvd = call("POST", f"/disruptions/{rep['id']}/mvd", {"planFrom": "17:00"})
    call("POST", f"/mvds/{mvd['id']}/accept")
    rec = call("POST", "/rearrange", {"date": "2026-11-02"})
    (d,) = rec["result"]["needsDecision"]
    assert d["taskId"] == tight["id"] and [o["code"] for o in d["options"] if o["available"]] == ["C", "E"]
    call("POST", f"/rearrangements/{rec['id']}/choose", {"taskId": tight["id"], "option": "C"})
    assert call("POST", f"/rearrangements/{rec['id']}/accept")["status"] == "accepted"
    t = call("GET", f"/tasks/{tight['id']}")
    assert (t["plannedDate"], t["plannedStart"], t["plannedEnd"]) == ("2026-11-03", "17:00", "18:00")
    assert t["rearrangeReason"].startswith("Shorten it to 60 min")
