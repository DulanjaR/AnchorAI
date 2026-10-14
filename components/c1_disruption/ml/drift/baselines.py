"""Baselines for ML Model 1 (docs/METHODOLOGY.md §3). Same interface as DriftModel:
fit(records) and predict_log(records) → log drift per record.

  B0  drift = 1.0 (log 0): trust the plan
  B1  global mean log ratio
  B2  per-student mean log ratio; global mean when the student has n = 0
  B3  shrinkage only, no forest: B1 + w · (student mean − global mean), w = n/(n+k),
      k chosen by the same leave-one-record-out rule as the model
"""
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from components.c1_disruption.ml.drift.data import log_drift
from components.c1_disruption.ml.drift.model import choose_k


class _Base:
    name = ""

    def fit(self, records: Sequence[Mapping[str, Any]]) -> "_Base":
        y = log_drift(records)
        self.global_mean = float(y.mean()) if len(y) else 0.0
        by_student: dict[str, list[float]] = defaultdict(list)
        for r, v in zip(records, y):
            by_student[r["studentId"]].append(float(v))
        self.students = {s: (len(v), float(np.mean(v))) for s, v in by_student.items()}
        self._fit_extra(records, y)
        return self

    def _fit_extra(self, records: Sequence[Mapping[str, Any]], y: np.ndarray) -> None:
        pass

    def predict_log(self, records: Sequence[Mapping[str, Any]]) -> np.ndarray:
        return np.array([self._one(r["studentId"]) for r in records], dtype=float)

    def _one(self, student_id: str) -> float:
        raise NotImplementedError


class B0NoDrift(_Base):
    name = "B0 drift = 1.0"

    def fit(self, records: Sequence[Mapping[str, Any]]) -> "B0NoDrift":
        return self

    def _one(self, student_id: str) -> float:
        return 0.0


class B1GlobalMean(_Base):
    name = "B1 global mean"

    def _one(self, student_id: str) -> float:
        return self.global_mean


class B2StudentMean(_Base):
    name = "B2 per-student mean"

    def _one(self, student_id: str) -> float:
        n, mean = self.students.get(student_id, (0, 0.0))
        return mean if n else self.global_mean


class B3ShrinkageOnly(_Base):
    name = "B3 shrinkage only"

    def _fit_extra(self, records: Sequence[Mapping[str, Any]], y: np.ndarray) -> None:
        self.k = choose_k([r["studentId"] for r in records], y - self.global_mean)

    def _one(self, student_id: str) -> float:
        n, mean = self.students.get(student_id, (0, 0.0))
        w = n / (n + self.k) if (n + self.k) > 0 else 0.0
        return self.global_mean + w * (mean - self.global_mean)


BASELINES = (B0NoDrift, B1GlobalMean, B2StudentMean, B3ShrinkageOnly)
