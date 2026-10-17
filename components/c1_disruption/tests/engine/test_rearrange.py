"""Rearranger rules not covered by golden R01–R08 (engine/rearrange.py)."""
import copy
import json
from pathlib import Path

from components.c1_disruption.engine.rearrange import rearrange

GOLDEN = Path(__file__).parents[1] / "golden" / "rearrange"


def golden(rid):
    return json.loads((GOLDEN / f"{rid}.json").read_text(encoding="utf-8"))["input"]


def task(**extra):
    return {"id": "M1", "title": "Report", "type": "Digital", "priority": "Medium", "deadline": "2026-11-05T23:59",
            "durationMinutes": 90, "splittable": False, "delegable": False, "location": None, **extra}


def data(days, moved=(), effort=(), today="2026-11-02", frm="2026-11-03T00:00"):
    return {"today": today, "from": frm, "horizonDays": 7, "days": days, "moved": list(moved), "effort": list(effort)}


def evening(date, start="19:00", end="21:00", location="Home"):
    return {"date": date, "windows": [{"start": start, "end": end, "location": location}], "fixed": [], "planned": []}


def test_the_input_is_never_changed():
    for rid in ("R04", "R05", "R07"):
        inp = golden(rid)
        before = copy.deepcopy(inp)
        rearrange(inp)
        assert inp == before


def test_the_deadline_day_is_used_only_when_nothing_earlier_fits():
    out = rearrange(data([evening("2026-11-03", "19:00", "20:00"), evening("2026-11-05", "08:00", "12:00")], [task()]))
    (p,) = out["placements"]
    assert (p["date"], p["start"], p["end"]) == ("2026-11-05", "08:00", "09:30")
    assert p["reason"].startswith("Placed on Thu 5 Nov (its deadline day), 08:00–09:30: no earlier day has a free gap of 90 min.")


def test_nothing_is_placed_after_the_deadline_time_or_past_the_horizon():
    late = rearrange(data([evening("2026-11-05", "20:00", "23:00")], [task(deadline="2026-11-05T21:00")]))
    assert late["placements"] == [] and late["needsDecision"][0]["shortfallMinutes"] == 30  # only 20:00–21:00 counts
    far = rearrange(data([evening("2026-11-12")], [task(deadline="2026-11-20T23:59")]))  # day 10 > 7-day horizon
    assert far["placements"] == [] and far["needsDecision"]


def test_meeting_tasks_are_not_split_by_default():
    out = rearrange(data([evening("2026-11-03", "19:00", "20:00"), evening("2026-11-04", "19:00", "20:00")],
                         [task(type="Meeting", splittable=None)]))
    assert out["placements"] == []
    assert out["needsDecision"][0]["options"][1]["reason"] == "Not possible: this task cannot be split."


def test_no_free_time_at_all_still_offers_e():
    out = rearrange(data([], [task()]))
    d = out["needsDecision"][0]
    assert d["reason"] == "There is no free time before the deadline (Thu 5 Nov 23:59). You choose:"
    assert [o["available"] for o in d["options"]] == [False, False, False, False, True]
    assert d["shortfallMinutes"] == 90


def test_effort_early_warning_when_work_left_exceeds_free_time():
    effort = {"id": "E1", "title": "Project report", "type": "Digital", "priority": "Medium", "deadline": "2026-11-06T23:59",
              "totalEffortMinutes": 400, "actualMinutesDone": 0, "minSession": 30, "maxSession": 120, "sessions": []}
    out = rearrange(data([evening(f"2026-11-0{d}") for d in (3, 4, 5)], effort=[effort]))
    (w,) = out["warnings"]
    assert w["code"] == "EFFORT_AT_RISK" and "400 min of work left but only 360 min free" in w["message"]
    assert [p["minutes"] for p in out["placements"]] == [120, 120, 120]  # capped at maxSession


def test_effort_extra_minutes_go_to_the_earliest_days():
    effort = {"id": "E1", "title": "Essay", "type": "Analog", "priority": "Low", "deadline": "2026-11-07T23:59",
              "totalEffortMinutes": 190, "actualMinutesDone": 0, "sessions": []}
    out = rearrange(data([evening(f"2026-11-0{d}") for d in (3, 4, 5, 6)], effort=[effort]))
    assert [p["minutes"] for p in out["placements"]] == [50, 50, 45, 45]
    assert "45–50 min a day" in out["placements"][0]["reason"]


def test_several_moved_tasks_share_the_free_time_in_fi_order():
    urgent = task(id="U", priority="High", durationMinutes=60, deadline="2026-11-04T23:59")
    later = task(id="L", priority="Low", durationMinutes=60, deadline="2026-11-08T23:59")
    out = rearrange(data([evening("2026-11-03", "19:00", "20:00"), evening("2026-11-04", "19:00", "20:00")], [later, urgent]))
    assert [(p["taskId"], p["date"]) for p in out["placements"]] == [("U", "2026-11-03"), ("L", "2026-11-04")]


def test_free_time_of_a_task_waiting_for_a_decision_is_kept_for_it():
    # PROPOSED (17 Oct 2026): the urgent task U cannot be placed (needs 120, only Tue 17:00–18:00
    # before its deadline); until the student decides, the less urgent L may not take that hour.
    urgent = task(id="U", priority="High", durationMinutes=120, deadline="2026-11-03T23:59", splittable=True)
    later = task(id="L", priority="Low", durationMinutes=60, deadline="2026-11-08T23:59")
    days = [evening("2026-11-03", "17:00", "18:00"), evening("2026-11-04", "17:00", "18:00")]
    out = rearrange(data(days, [later, urgent]))
    assert [d["taskId"] for d in out["needsDecision"]] == ["U"]
    assert [(p["taskId"], p["date"]) for p in out["placements"]] == [("L", "2026-11-04")]
    assert "only 60 min are free (Tue 17:00–18:00)" in out["needsDecision"][0]["reason"]
