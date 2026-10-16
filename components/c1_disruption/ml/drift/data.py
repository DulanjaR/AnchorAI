"""Training records for ML Model 1 and their features.

A record is one completed task:
    studentId, taskType, priority, estimatedMinutes, actualMinutes,
    date ('YYYY-MM-DD'), startHour (0–23), overlapMinutes (optional: minutes of a
    confirmed disruption inside the task's start–done span), category (optional:
    coding / writing / reading / revision, 16 Oct 2026; missing = None)

Target y = log(actual ÷ estimated) (log drift; 0 = on time).
"""
import math
from datetime import date as Date
from typing import Any, Iterable, Mapping, NotRequired, TypedDict

import numpy as np

from components.c1_disruption.engine import config as engine_config
from components.c1_disruption.ml.drift import settings


class DriftRecord(TypedDict):
    studentId: str
    taskType: str
    priority: str
    estimatedMinutes: float
    actualMinutes: NotRequired[float | None]  # None for a query (not done yet)
    date: str
    startHour: int
    overlapMinutes: NotRequired[float]
    category: NotRequired[str | None]


FEATURE_NAMES: tuple[str, ...] = (
    *(f"type_{t}" for t in engine_config.TASK_TYPES),
    "log_estimated_minutes",
    "start_hour",
    "weekday",
    "weekend",
    "priority_score",
)
# Added after FEATURE_NAMES when the model uses the category (settings.USE_CATEGORY).
CATEGORY_FEATURE_NAMES: tuple[str, ...] = tuple(f"category_{c}" for c in engine_config.TASK_CATEGORIES)


def feature_names(use_category: bool = False) -> tuple[str, ...]:
    return FEATURE_NAMES + (CATEGORY_FEATURE_NAMES if use_category else ())


def weekday(date_str: str) -> int:
    """Monday = 0 … Sunday = 6."""
    return Date.fromisoformat(date_str).weekday()


def features(records: Iterable[Mapping[str, Any]], use_category: bool = False) -> np.ndarray:
    """Feature matrix in feature_names(use_category) order. The student is NOT a feature:
    the pooled forest is the same for everyone; personalisation is the shrinkage term.
    A missing or unknown category gives all-zero category columns (graceful)."""
    rows = []
    for r in records:
        if r["taskType"] not in engine_config.TASK_TYPES:
            raise ValueError(f"Unknown task type '{r['taskType']}'")
        day = weekday(r["date"])
        rows.append([
            *(1.0 if r["taskType"] == t else 0.0 for t in engine_config.TASK_TYPES),
            math.log(r["estimatedMinutes"]),
            float(r["startHour"]),
            float(day),
            1.0 if day >= 5 else 0.0,
            float(engine_config.PRIORITY_SCORE[r["priority"]]),
            *((1.0 if r.get("category") == c else 0.0 for c in engine_config.TASK_CATEGORIES) if use_category else ()),
        ])
    return np.array(rows, dtype=float).reshape(-1, len(feature_names(use_category)))


def log_drift(records: Iterable[Mapping[str, Any]]) -> np.ndarray:
    return np.array([math.log(r["actualMinutes"] / r["estimatedMinutes"]) for r in records], dtype=float)


def clean(records: Iterable[DriftRecord]) -> list[DriftRecord]:
    """Exclusion rule (CLAUDE.md §3.6): time lost to a confirmed disruption is not
    task time. Subtract the overlap; drop the record when that is not reliable.
    Records without an actual are dropped (nothing to learn from)."""
    kept: list[DriftRecord] = []
    for r in records:
        actual = r.get("actualMinutes")
        if actual is None or actual <= 0 or r["estimatedMinutes"] <= 0:
            continue
        overlap = r.get("overlapMinutes") or 0
        if overlap:
            remaining = actual - overlap
            if overlap > settings.MAX_OVERLAP_SHARE * actual or remaining < settings.MIN_CLEAN_MINUTES:
                continue
            r = {**r, "actualMinutes": remaining, "overlapMinutes": 0}
        kept.append(r)
    return kept
