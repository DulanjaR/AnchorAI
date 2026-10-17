"""Rearranger golden scenarios R01–R08 (owner-approved 17 Oct 2026, written before the code):
engine/rearrange.py must reproduce `expected` exactly, reasons included."""
import json
from pathlib import Path

import pytest

from components.c1_disruption.engine.rearrange import rearrange

FILES = sorted((Path(__file__).parent / "rearrange").glob("R*.json"))


def test_there_are_eight_approved_scenarios():
    assert [f.stem for f in FILES] == [f"R0{i}" for i in range(1, 9)]
    assert all(json.loads(f.read_text(encoding="utf-8"))["status"].startswith("APPROVED") for f in FILES)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_rearranger_matches_the_golden_scenario(path):
    s = json.loads(path.read_text(encoding="utf-8"))
    assert rearrange(s["input"]) == s["expected"]


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_options_shape(path):
    exp = json.loads(path.read_text(encoding="utf-8"))["expected"]
    for d in exp["needsDecision"]:
        assert [o["code"] for o in d["options"]] == list("ABCDE") and d["options"][-1]["available"]
