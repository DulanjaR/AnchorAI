"""The JS-compatible number helpers (why: see engine/jsnum.py)."""
import pytest

from components.c1_disruption.engine.jsnum import js_round, number_text, to_fixed_number


@pytest.mark.parametrize(
    ("x", "expected"),
    [(0.5, 1), (1.5, 2), (2.5, 3), (202.5, 203), (-0.5, 0), (-1.5, -1), (0.49999999999999994, 0), (333.33, 333)],
)
def test_js_round_halves_go_up(x, expected):
    # Python's round() would give 0, 2, 2, 202 for the first four.
    assert js_round(x) == expected


@pytest.mark.parametrize(
    ("x", "digits", "expected"),
    [(0.0625, 3, 0.063), (0.20833, 3, 0.208), (1 / 0.7, 3, 1.429), (12.5, 3, 12.5), (1.005, 2, 1.0)],
)
def test_to_fixed_number_uses_the_exact_binary_value(x, digits, expected):
    # 1.005 is really 1.00499999999999989…, so JS (1.005).toFixed(2) is "1.00".
    assert to_fixed_number(x, digits) == expected


@pytest.mark.parametrize(
    ("x", "text"),
    [(50.0, "50"), (0, "0"), (33.3, "33.3"), (0.1 + 0.2, "0.30000000000000004"), (1e-5, "0.00001"), (-2.0, "-2")],
)
def test_number_text_like_js_string(x, text):
    assert number_text(x) == text
