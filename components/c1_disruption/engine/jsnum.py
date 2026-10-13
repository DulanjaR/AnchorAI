"""Number rounding and printing exactly as the Node engine did it.

Why this exists: the golden spec (tests/golden/) was produced by JavaScript, and
Python's built-ins differ in small ways that change visible output:
  - round() rounds halves to even; JS Math.round rounds halves up (20.25 → 20.3 in JS).
  - '%.3f' rounds an exact binary tie to even; JS toFixed picks the larger value.
  - str(50.0) is '50.0'; JS prints 50 ("Shortened by 50%").
Pure functions, positive and negative inputs both handled like JS.
"""
import math
from decimal import ROUND_HALF_UP, Decimal


def js_round(x: float) -> int:
    """JS Math.round: nearest integer, halves towards +infinity."""
    floor = math.floor(x)
    # x - floor is exact for floats, so the 0.5 comparison has no rounding error.
    return floor + 1 if x - floor >= 0.5 else floor


def to_fixed_number(x: float, digits: int) -> float:
    """JS Number(x.toFixed(digits)) for x >= 0 (Fi is always positive)."""
    # Decimal(x) is the exact binary value, so ties are real ties, as in toFixed.
    return float(Decimal(x).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP))


def number_text(x: float | int) -> str:
    """JS String(number): 50.0 → '50', 33.3 → '33.3'."""
    if isinstance(x, bool):
        raise TypeError("number_text expects a number, not a bool")
    if float(x).is_integer() and abs(x) < 1e21:
        return str(int(x))
    text = repr(float(x))
    if "e" in text and 1e-6 <= abs(x) < 1e21:
        # Python switches to exponent notation earlier than JS does.
        text = format(Decimal(text), "f")
    return text
