"""ML Model 1 — Timeline Drift Predictor (docs/METHODOLOGY.md §3).

    ŷ = f(x) + w · r̄_s,   w = n_s / (n_s + k)

f = pooled quantile regression forest on log drift (all students), r̄_s = the
student's mean residual y − f(x) on their own training records, computed from
OUT-OF-FOLD forest predictions (in-sample forest residuals are close to 0 and
would hide a student's real drift). k is chosen from settings.K_GRID by
leave-one-record-out on the training data only. A day-1 student (n = 0) gets f(x).
The q10/q90 range is shifted by the same w · r̄_s.

Library: quantile-forest (RandomForestQuantileRegressor, scikit-learn API); see
DECISIONS.md for why.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from quantile_forest import RandomForestQuantileRegressor
from sklearn.model_selection import KFold

from components.c1_disruption.ml.drift import settings
from components.c1_disruption.ml.drift.data import features, log_drift


@dataclass(frozen=True)
class DriftPrediction:
    log_point: float
    log_low: float
    log_high: float
    n: int  # the student's training records
    weight: float  # w = n / (n + k)

    @property
    def drift(self) -> float:
        return float(np.exp(self.log_point))

    def corrected_minutes(self, estimated_minutes: float) -> tuple[float, float, float]:
        """(point, low, high) minutes for a task estimated at `estimated_minutes`."""
        return tuple(float(estimated_minutes * np.exp(v)) for v in (self.log_point, self.log_low, self.log_high))


def choose_k(students: Sequence[str], residuals: np.ndarray, grid: Sequence[float] = settings.K_GRID) -> float:
    """k with the lowest leave-one-record-out absolute error of the shrunk residual.

    For record i of student s the shrinkage term uses only s's OTHER records:
    n' = n_s − 1, mean of the other residuals, w = n' / (n' + k).
    Ties → the larger k (more pooling, the safer choice).
    """
    by_student: dict[str, list[int]] = defaultdict(list)
    for i, s in enumerate(students):
        by_student[s].append(i)
    best_k, best_err = grid[-1], float("inf")
    for k in sorted(grid, reverse=True):
        errors = []
        for idx in by_student.values():
            r = residuals[idx]
            total, n = r.sum(), len(r)
            for value in r:
                n_other = n - 1
                mean_other = (total - value) / n_other if n_other else 0.0
                w = n_other / (n_other + k) if (n_other + k) > 0 else 0.0
                errors.append(abs(value - w * mean_other))
        err = float(np.mean(errors)) if errors else float("inf")
        if err < best_err - 1e-12:
            best_k, best_err = k, err
    return best_k


class DriftModel:
    """Pooled forest + per-student shrinkage. fit() on cleaned records (data.clean)."""

    def __init__(
        self,
        k: float | None = None,
        quantiles: tuple[float, float] = settings.QUANTILES,
        n_estimators: int = settings.N_ESTIMATORS,
        random_state: int = settings.RANDOM_STATE,
    ) -> None:
        self.k_fixed = k  # None = choose by cross-validation
        self.quantiles = quantiles
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.k: float | None = None
        self.forest: RandomForestQuantileRegressor | None = None
        self.offsets: dict[str, tuple[int, float]] = {}  # student → (n, mean residual)

    @property
    def trained(self) -> bool:
        return self.forest is not None

    def _forest(self) -> RandomForestQuantileRegressor:
        return RandomForestQuantileRegressor(
            n_estimators=self.n_estimators,
            min_samples_leaf=settings.MIN_SAMPLES_LEAF,
            random_state=self.random_state,
        )

    def fit(self, records: Sequence[Mapping[str, Any]]) -> "DriftModel":
        if len(records) < 2:
            raise ValueError("Need at least 2 training records")
        X, y = features(records), log_drift(records)
        students = [r["studentId"] for r in records]

        # Out-of-fold pooled predictions → honest residuals per record.
        oof = np.empty_like(y)
        folds = min(settings.RESIDUAL_FOLDS, len(records))
        for train_idx, test_idx in KFold(folds, shuffle=True, random_state=self.random_state).split(X):
            f = self._forest().fit(X[train_idx], y[train_idx])
            oof[test_idx] = f.predict(X[test_idx], quantiles="mean")
        residuals = y - oof

        self.k = self.k_fixed if self.k_fixed is not None else choose_k(students, residuals)
        sums: dict[str, list[float]] = defaultdict(list)
        for s, r in zip(students, residuals):
            sums[s].append(float(r))
        self.offsets = {s: (len(v), float(np.mean(v))) for s, v in sums.items()}
        self.forest = self._forest().fit(X, y)
        return self

    def weight(self, student_id: str) -> tuple[int, float]:
        n, _ = self.offsets.get(student_id, (0, 0.0))
        k = self.k or 0.0
        return n, (n / (n + k) if (n + k) > 0 else 0.0)

    def predict(self, records: Sequence[Mapping[str, Any]]) -> list[DriftPrediction]:
        if self.forest is None:
            raise RuntimeError("DriftModel is not trained")
        if not records:
            return []
        X = features(records)
        point = self.forest.predict(X, quantiles="mean")
        low, high = np.asarray(self.forest.predict(X, quantiles=list(self.quantiles))).T
        out = []
        for r, p, lo, hi in zip(records, point, low, high):
            n, w = self.weight(r["studentId"])
            shift = w * self.offsets.get(r["studentId"], (0, 0.0))[1]
            out.append(DriftPrediction(float(p + shift), float(lo + shift), float(hi + shift), n, w))
        return out

    def predict_log(self, records: Sequence[Mapping[str, Any]]) -> np.ndarray:
        return np.array([p.log_point for p in self.predict(records)])

    def predict_interval(self, records: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
        preds = self.predict(records)
        return np.array([p.log_low for p in preds]), np.array([p.log_high for p in preds])
