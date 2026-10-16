"""Evaluation of ML Model 1 and its baselines (docs/METHODOLOGY.md §3).

  leave_one_student_out  cold start: train on everyone else, predict the held-out
                         student with n = 0 (their records are never seen)
  rolling_origin         warm: for each student and day d, train on all other
                         students + this student's days BEFORE d, predict day d
Measures: MAE in minutes, MAE of the log ratio, interval coverage (models with a
range), learning curve (MAE against the student's n at prediction time).

A "factory" is a no-argument callable returning an unfitted model or baseline
(anything with fit(records) and predict_log(records); a range if it also has
predict_interval). Every fold builds a fresh one, so nothing leaks between folds.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from components.c1_disruption.ml.drift.data import log_drift

Records = Sequence[Mapping[str, Any]]
Factory = Callable[[], Any]


@dataclass
class Predictions:
    """One row per predicted record."""

    records: list[Mapping[str, Any]] = field(default_factory=list)
    log_pred: list[float] = field(default_factory=list)
    log_low: list[float | None] = field(default_factory=list)
    log_high: list[float | None] = field(default_factory=list)
    n_seen: list[int] = field(default_factory=list)  # the student's training records at prediction time
    trusted: list[bool | None] = field(default_factory=list)  # earned-trust gate open (None: no gate)

    def add(self, records: Records, model: Any, n_seen: int) -> None:
        if not records:
            return
        self.records.extend(records)
        self.log_pred.extend(float(v) for v in model.predict_log(records))
        if hasattr(model, "predict_interval"):
            low, high = model.predict_interval(records)
            self.log_low.extend(float(v) for v in low)
            self.log_high.extend(float(v) for v in high)
        else:
            self.log_low.extend([None] * len(records))
            self.log_high.extend([None] * len(records))
        self.n_seen.extend([n_seen] * len(records))
        gate = getattr(model, "is_trusted", None)
        self.trusted.extend(gate(r["studentId"]) if gate else None for r in records)


def score(p: Predictions) -> dict[str, float | None]:
    """MAE (minutes), MAE (log ratio), interval coverage."""
    if not p.records:
        return {"maeMinutes": None, "maeLog": None, "coverage": None, "n": 0, "trustedShare": None}
    y = log_drift(p.records)
    pred = np.array(p.log_pred)
    est = np.array([r["estimatedMinutes"] for r in p.records], dtype=float)
    actual = np.array([r["actualMinutes"] for r in p.records], dtype=float)
    result: dict[str, float | None] = {
        "maeMinutes": float(np.mean(np.abs(est * np.exp(pred) - actual))),
        "maeLog": float(np.mean(np.abs(pred - y))),
        "coverage": None,
        "n": len(y),
        # Share of predictions where the earned-trust gate let the model correct (None: no gate).
        "trustedShare": (float(np.mean([bool(t) for t in p.trusted]))
                         if p.trusted and all(t is not None for t in p.trusted) else None),
    }
    if all(v is not None for v in p.log_low):
        low, high = np.array(p.log_low, dtype=float), np.array(p.log_high, dtype=float)
        result["coverage"] = float(np.mean((y >= low) & (y <= high)))
    return result


def learning_curve(p: Predictions, bins: Sequence[int] = (0, 1, 5, 10, 20, 40)) -> list[dict[str, Any]]:
    """MAE (minutes and log) per bin of n (the student's records when predicted).
    A bin [a, b) holds predictions made when the student had a ≤ n < b records."""
    edges = list(bins) + [10**9]
    rows = []
    for lo, hi in zip(edges, edges[1:]):
        idx = [i for i, n in enumerate(p.n_seen) if lo <= n < hi]
        sub = Predictions(
            [p.records[i] for i in idx], [p.log_pred[i] for i in idx], [p.log_low[i] for i in idx],
            [p.log_high[i] for i in idx], [p.n_seen[i] for i in idx],
            [p.trusted[i] for i in idx] if p.trusted else [],
        )
        rows.append({"nFrom": lo, "nTo": None if hi == 10**9 else hi, **score(sub)})
    return rows


def leave_one_student_out(records: Records, factory: Factory) -> Predictions:
    out = Predictions()
    for student in sorted({r["studentId"] for r in records}):
        train = [r for r in records if r["studentId"] != student]
        test = [r for r in records if r["studentId"] == student]
        out.add(test, factory().fit(train), n_seen=0)
    return out


def rolling_origin(records: Records, factory: Factory, min_history_days: int = 1, step_days: int = 1) -> Predictions:
    """For each student, origin days d = their (min_history_days+1)-th day onwards,
    every `step_days`; predict all of the student's records on days [d, d+step)
    from everyone else's records + the student's records before d."""
    out = Predictions()
    by_student: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for r in records:
        by_student[r["studentId"]].append(r)
    for student, own in sorted(by_student.items()):
        others = [r for r in records if r["studentId"] != student]
        days = sorted({r["date"] for r in own})
        for i in range(min_history_days, len(days), step_days):
            window = set(days[i:i + step_days])
            past = [r for r in own if r["date"] < days[i]]
            test = [r for r in own if r["date"] in window]
            out.add(test, factory().fit(others + past), n_seen=len(past))
    return out
