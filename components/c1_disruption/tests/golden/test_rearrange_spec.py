"""Rearranger golden scenarios R01–R08 (17 Oct 2026): DRAFT spec, written before any code.
Only the files' shape is checked until the owner approves them and engine/rearrange.py exists."""
import json
from pathlib import Path

import pytest

FILES = sorted((Path(__file__).parent / "rearrange").glob("R*.json"))


def test_there_are_eight_scenarios():
    assert [f.stem for f in FILES] == [f"R0{i}" for i in range(1, 9)]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_scenario_shape(path):
    s = json.loads(path.read_text(encoding="utf-8"))
    assert s["id"] == path.stem and s["status"].startswith("DRAFT") and s["workings"]
    inp, exp = s["input"], s["expected"]
    assert inp["horizonDays"] == 7 and (inp["moved"] or inp["effort"])
    for p in exp["placements"]:
        assert p["reason"] and p["start"] < p["end"]
    for d in exp["needsDecision"]:
        assert [o["code"] for o in d["options"]] == list("ABCDE")
        assert all(o["reason"] for o in d["options"]) and d["options"][-1]["available"]  # E is always offered
    assert not (exp["placements"] and exp["needsDecision"] and {p["taskId"] for p in exp["placements"]}
                & {d["taskId"] for d in exp["needsDecision"]})
