"""The PP1 demo (demo/pp1_demo.py) keeps working end to end and shows all four tags."""
from components.c1_disruption.demo import pp1_demo


def test_pp1_demo_runs_end_to_end_and_shows_every_tag():
    lines = []
    result = pp1_demo.run(out=lines.append)
    plan = {t["id"]: t for t in result["mvd"]["plan"]["tasks"]}
    by_title = {t["title"]: plan[t["id"]] for t in result["tasks"]}
    assert {t["tag"] for t in plan.values()} == {"Keep", "Reduce", "Move", "Delegate"}
    # Digital task during the power cut goes after it; urgent analog work fills the outage.
    assert (by_title["Lab report (submit tonight)"]["start"], by_title["Maths problem sheet"]["start"]) == ("13:30", "09:00")
    assert by_title["Online course video"]["compressionPct"] == 25.0
    assert all(t["explanation"] for t in plan.values())
    # Accepted: the tasks carry the tags Components 3 and 4 read; the decision is logged.
    assert [t["mvdTag"] for t in result["tasks"]] == [plan[t["id"]]["tag"] for t in result["tasks"]]
    assert (result["feedback"][0]["action"], result["feedback"][0]["reward"]) == ("accept", 1.0)
    assert any("Component 4 reads Delegate: ['Group slides']" in line for line in lines)
