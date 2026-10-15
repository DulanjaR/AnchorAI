"""Transparent resumption-difficulty rule. Mirrors app/static/core.js (checked by shared test vectors)."""
from __future__ import annotations

import math
from typing import Any

LEVELS = ("Low", "Medium", "High")
COMPLEXITY = {"simple": 0, "moderate": 1, "complex": 2}
MAX_SCORE = 8

DEPTH = {
    "Low": {"name": "Short", "suggested": ["workingPoint", "nextStep"]},
    "Medium": {"name": "Standard", "suggested": ["goal", "workingPoint", "problem", "nextStep"]},
    "High": {"name": "Full", "suggested": ["goal", "completed", "workingPoint", "problem", "nextStep", "resources"]},
}


def _valid_minutes(minutes: Any) -> float | None:
    try:
        value = float(minutes)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or value < 0:
        return None
    return value


def format_minutes(minutes: Any) -> str:
    m = _valid_minutes(minutes)
    if m is None:
        return "an unknown time"
    if m < 1:
        return "less than a minute"
    if m < 60:
        return f"{round(m)} min"
    if m < 1440:
        h = m / 60
        return f"{int(h) if float(h).is_integer() else round(h, 1)} h"
    d = m / 1440
    if float(d).is_integer():
        return "1 day" if int(d) == 1 else f"{int(d)} days"
    return f"{round(d, 1)} days"


def duration_points(minutes: Any) -> int:
    m = _valid_minutes(minutes)
    if m is None or m < 15:
        return 0
    if m < 60:
        return 1
    if m < 240:
        return 2
    return 3


def open_item_points(n: int) -> int:
    if n >= 5:
        return 2
    if n >= 2:
        return 1
    return 0


def predict_difficulty(minutes: Any, complexity: str = "moderate", open_items: Any = 0, type: str = "other") -> dict:
    """Hand-set rule. Direction (longer interruption, more complex task -> harder) follows Model 1b;
    thresholds are placeholders until pilot data recalibrates them."""
    complexity = complexity if complexity in COMPLEXITY else "moderate"
    try:
        open_items = max(0, int(float(open_items or 0)))
    except (TypeError, ValueError):
        open_items = 0
    switches = type == "other_task"

    d = duration_points(minutes)
    c = COMPLEXITY[complexity]
    o = open_item_points(open_items)
    s = 1 if switches else 0
    score = d + c + o + s
    level = "High" if score >= 5 else "Medium" if score >= 3 else "Low"

    m = _valid_minutes(minutes)
    reasons = [
        {"text": f"Away about {format_minutes(m)}" if m is not None else "Time away not given", "points": d},
        {"text": f"Task complexity: {complexity}", "points": c},
        {"text": f"{open_items} unfinished item{'' if open_items == 1 else 's'}", "points": o},
        {
            "text": "Interrupted by another work task" if switches else "Interruption does not need another work task",
            "points": s,
        },
    ]
    return {"score": score, "max": MAX_SCORE, "level": level, "depth": DEPTH[level], "reasons": reasons}
