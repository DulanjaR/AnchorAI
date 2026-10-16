"""The PP1 demo (demo/pp1_demo.py) keeps working end to end: SYNTHETIC persona P01, Model 1 on
with the earned-trust gate open, MVD, accept, tags for Components 3 and 4."""
import pytest

from components.c1_disruption.demo import pp1_demo


@pytest.fixture(scope="module")
def demo():
    lines = []
    return pp1_demo.run(out=lines.append), lines


def test_p01_has_enough_history_for_the_gate_to_open(demo):
    result, lines = demo
    assert pp1_demo.USER == "P01"
    trust = result["trust"]
    assert trust.trusted and trust.n_recent == 20 and trust.model_mae < trust.b0_mae
    assert any(line.startswith("Earned-trust gate for P01: OPEN.") for line in lines)


def test_model_1_corrects_p01s_durations_in_the_plan(demo):
    result, _ = demo
    logs = result["mvd"]["taskLog"]
    assert result["mvd"]["modelOn"] is True
    assert {log["correctionSource"] for log in logs} == {"model"}
    assert all(log["correctedLowHours"] <= log["correctedHours"] <= log["correctedHighHours"] for log in logs)
    lab = next(log for log in logs if log["estimatedHours"] == 2 and log["correctedHours"] > 2.4)
    assert lab  # P01 runs over on Digital work (planted drift 1.35)


def test_pp1_demo_runs_end_to_end(demo):
    result, lines = demo
    plan = {t["id"]: t for t in result["mvd"]["plan"]["tasks"]}
    by_title = {t["title"]: plan[t["id"]] for t in result["tasks"]}
    # Digital work goes after the power cut; urgent analog work fills the outage.
    assert by_title["Lab report (submit tonight)"]["tag"] == "Keep"
    assert by_title["Lab report (submit tonight)"]["start"] == "13:30"
    assert by_title["Maths problem sheet"]["start"] == "09:00"
    assert by_title["Group slides"]["tag"] == "Delegate"
    assert all(t["explanation"] for t in plan.values())
    # Accepted: the tasks carry the tags Components 3 and 4 read; the decision is logged.
    assert [t["mvdTag"] for t in result["tasks"]] == [plan[t["id"]]["tag"] for t in result["tasks"]]
    assert (result["feedback"][0]["action"], result["feedback"][0]["reward"]) == ("accept", 1.0)
    assert any("Component 4 reads Delegate: ['Group slides']" in line for line in lines)
