import re

import pytest

from components.c1_disruption.engine.errors import EngineError
from components.c1_disruption.engine.explain import (
    FREE_TIME_NOTE,
    TEMPLATES,
    explain_protected,
    explain_task,
    format_fi,
)

CTX = {"disruptionType": "power_outage", "windowStart": "09:00", "windowEnd": "12:00"}


def task(**over):
    return {
        "priority": "High", "fi": 0.20833, "daysUntilDeadline": 0, "start": "09:00", "end": "11:00",
        "compressionPct": 0, "deadlineRisk": False, **over,
    }


ALL_CODES = [
    "KEEP_URGENT", "FITS_FULLY", "OUTSIDE_DISRUPTION_WINDOW", "REDUCE_BUDGET",
    "BLOCKED_BY_DISRUPTION", "LOW_URGENCY", "TIME_TAKEN_BY_DISRUPTION", "BUDGET_EXCEEDED", "DELEGABLE",
]


def test_every_reason_code_has_a_template():
    assert set(TEMPLATES) == set(ALL_CODES)
    for code in ALL_CODES:
        assert explain_task(task(reason=code), CTX)


def test_keep_explanation_names_deadline_priority_fi_and_slot():
    text = explain_task(task(reason="KEEP_URGENT"), CTX)
    for part in ("due today", "High priority", "Fi 0.208", "09:00–11:00"):
        assert part in text


def test_reduce_explanation_states_how_much_was_cut_like_js_prints_numbers():
    assert "33.3%" in explain_task(task(reason="REDUCE_BUDGET", compressionPct=33.3), CTX)
    assert "Shortened by 50% " in explain_task(task(reason="REDUCE_BUDGET", compressionPct=50.0), CTX)


def test_disruption_explanations_name_the_disruption_and_window():
    assert "power outage (09:00–12:00)" in explain_task(task(reason="BLOCKED_BY_DISRUPTION"), CTX)


def test_time_taken_names_the_unavailable_disruption():
    work = {"disruptionType": "urgent_work", "windowStart": "18:00", "windowEnd": "20:00"}
    assert explain_task(task(reason="TIME_TAKEN_BY_DISRUPTION"), work).startswith(
        "Moved to tomorrow: this time is taken by urgent work (18:00–20:00)"
    )


def test_deadline_risk_adds_a_warning():
    text = explain_task(task(reason="BUDGET_EXCEEDED", deadlineRisk=True), CTX)
    assert re.search(r"Warning: .*due today.*at risk", text)


def test_low_urgency_mentions_starting_early_only_with_free_time_left():
    moved = task(reason="LOW_URGENCY", fi=12.5, daysUntilDeadline=5)
    assert FREE_TIME_NOTE in explain_task(moved, {**CTX, "freeMinutesLeft": 90})
    assert FREE_TIME_NOTE not in explain_task(moved, {**CTX, "freeMinutesLeft": 0})
    assert FREE_TIME_NOTE not in explain_task(moved, CTX)


def test_free_time_note_is_only_for_low_urgency():
    assert "start it early" not in explain_task(task(reason="BUDGET_EXCEEDED"), {**CTX, "freeMinutesLeft": 90})


def test_unknown_reason_code_raises():
    with pytest.raises(EngineError, match="NOPE"):
        explain_task(task(reason="NOPE"), CTX)


@pytest.mark.parametrize(
    ("fi", "text"),
    [(0.20833, "0.208"), (12.5, "12.5"), (2.0, "2"), (0.5, "0.5"), (1 / 0.7, "1.429"), (0.0625, "0.063")],
)
def test_format_fi_like_js_tofixed(fi, text):
    # 0.0625 is an exact binary tie: JS toFixed(3) gives 0.063, Python '%.3f' gives 0.062.
    assert format_fi(fi) == text


def test_explain_protected_says_the_block_is_never_touched():
    text = explain_protected({"id": "lunch", "label": "Lunch", "start": "12:30", "end": "13:30"})
    assert re.search(r"Lunch, 12:30–13:30.*never moves or shortens", text)
    assert "(nap, " in explain_protected({"id": "nap", "start": "14:00", "end": "14:30"})
