"""ML Model 1 — Timeline Drift Predictor (docs/METHODOLOGY.md §3).

    ŷ = f(x) + w · r̄_s,   w = n_s / (n_s + k)

f = pooled quantile regression forest on log drift (all students); its point is the
median q50 (settings.POINT_QUANTILE, 16 Oct 2026). r̄_s = the student's mean residual
y − f(x) on their own training records, computed from OUT-OF-FOLD forest predictions
(in-sample forest residuals are close to 0 and would hide a student's real drift). k is
chosen from settings.K_GRID by leave-one-record-out on the training data only. The
q10/q90 range is shifted by the same w · r̄_s.

Earned-trust gate (settings.GATE_*, 16 Oct 2026): ŷ is used for a student only if, on
that student's most recent training records, it beat B0 (drift 1.0) by the margin.
Otherwise, and for a student with too little evidence (a day-1 student, n = 0), the
point is drift 1.0 (log 0) and the range is widened to contain it.

Library: quantile-forest (RandomForestQuantileRegressor, scikit-learn API); see
DECISIONS.md for why.
"""
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
from quantile_forest import RandomForestQuantileRegressor
from sklearn.model_selection import KFold

from components.c1_disruption.engine.config import TASK_CATEGORIES
from components.c1_disruption.ml.drift import settings
from components.c1_disruption.ml.drift.data import features, log_drift
from components.c1_disruption.ml.progress import ProgressFn, say


@dataclass(frozen=True)
class DriftPrediction:
    log_point: float
    log_low: float
    log_high: float
    n: int  # the student's training records
    weight: float  # w = n / (n + k)
    trusted: bool = True  # False = the gate is closed for this student: drift 1.0

    @property
    def drift(self) -> float:
        return float(np.exp(self.log_point))

    def corrected_minutes(self, estimated_minutes: float) -> tuple[float, float, float]:
        """(point, low, high) minutes for a task estimated at `estimated_minutes`."""
        return tuple(float(estimated_minutes * np.exp(v)) for v in (self.log_point, self.log_low, self.log_high))


@dataclass(frozen=True)
class Trust:
    """Gate evidence for one student (most recent records, honest predictions)."""

    n_recent: int
    model_mae: float | None  # minutes
    b0_mae: float | None     # minutes
    trusted: bool


def gate_evidence(
    records: Sequence[Mapping[str, Any]], y: np.ndarray, oof: np.ndarray, k: float,
    lookback: int = settings.GATE_LOOKBACK, min_records: int = settings.GATE_MIN_RECORDS,
    margin: float = settings.GATE_MARGIN,
) -> dict[str, Trust]:
    """For each student: on their `lookback` most recent records (by date), the model's
    honest prediction = out-of-fold forest point + w · mean residual of the student's
    records from EARLIER days (w with that earlier count). Compared with B0 (log 0) in
    minutes. Open only with >= min_records of evidence and model MAE < (1 − margin) · B0 MAE."""
    by_student: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(records):
        by_student[r["studentId"]].append(i)
    residuals = y - oof
    out = {}
    for student, idx in by_student.items():
        idx = sorted(idx, key=lambda i: (records[i]["date"], i))
        recent = idx[-lookback:] if lookback > 0 else []
        model_err, b0_err = [], []
        for i in recent:
            earlier = [j for j in idx if records[j]["date"] < records[i]["date"]]
            n = len(earlier)
            w = n / (n + k) if (n + k) > 0 else 0.0
            shift = w * float(np.mean(residuals[earlier])) if n else 0.0
            est, actual = records[i]["estimatedMinutes"], records[i]["actualMinutes"]
            model_err.append(abs(est * np.exp(oof[i] + shift) - actual))
            b0_err.append(abs(est - actual))
        m = float(np.mean(model_err)) if model_err else None
        b = float(np.mean(b0_err)) if b0_err else None
        trusted = len(recent) >= min_records and m is not None and m < (1 - margin) * b
        out[student] = Trust(len(recent), m, b, trusted)
    return out


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
        gate: bool = settings.GATE_ENABLED,
        point_quantile: float | str = settings.POINT_QUANTILE,
        use_category: bool = settings.USE_CATEGORY,
    ) -> None:
        self.k_fixed = k  # None = choose by cross-validation
        self.quantiles = quantiles
        self.n_estimators = n_estimators
        self.random_state = random_state
        self.gate = gate
        self.point_quantile = point_quantile  # 0.5 = median; "mean" = the model before 16 Oct 2026
        self.trust: dict[str, Trust] = {}  # student → gate evidence
        self.use_category = use_category  # optional task category as a feature (16 Oct 2026)
        self.category_used = False  # set by fit: True only if the training data has categories
        self.k: float | None = None
        self.forest: RandomForestQuantileRegressor | None = None
        self.offsets: dict[str, tuple[int, float]] = {}  # student → (n, mean residual)
        self.n_records = 0

    @property
    def trained(self) -> bool:
        return self.forest is not None

    def _forest(self) -> RandomForestQuantileRegressor:
        return RandomForestQuantileRegressor(
            n_estimators=self.n_estimators,
            min_samples_leaf=settings.MIN_SAMPLES_LEAF,
            random_state=self.random_state,
        )

    def fit(self, records: Sequence[Mapping[str, Any]], progress: ProgressFn = None) -> "DriftModel":
        if len(records) < 2:
            raise ValueError("Need at least 2 training records")
        # The category columns are added only if the training data has categories at all, so data
        # without them (CESAW) gives exactly the model without the feature (graceful degradation).
        self.category_used = self.use_category and any(r.get("category") in TASK_CATEGORIES for r in records)
        X, y = features(records, self.uses_category), log_drift(records)
        students = [r["studentId"] for r in records]

        # Out-of-fold pooled predictions → honest residuals per record.
        oof = np.empty_like(y)
        folds = min(settings.RESIDUAL_FOLDS, len(records))
        for fold, (train_idx, test_idx) in enumerate(KFold(folds, shuffle=True, random_state=self.random_state).split(X), 1):
            say(progress, f"training fold {fold}/{folds} ({len(train_idx)} records)…")
            f = self._forest().fit(X[train_idx], y[train_idx])
            oof[test_idx] = f.predict(X[test_idx], quantiles=self.point_quantile)
        residuals = y - oof

        self.k = self.k_fixed if self.k_fixed is not None else choose_k(students, residuals)
        sums: dict[str, list[float]] = defaultdict(list)
        for s, r in zip(students, residuals):
            sums[s].append(float(r))
        self.offsets = {s: (len(v), float(np.mean(v))) for s, v in sums.items()}
        say(progress, f"shrinkage k = {self.k}; earned-trust gate for {len(self.offsets)} students…")
        self.trust = gate_evidence(records, y, oof, self.k) if self.gate else {}
        say(progress, f"training the final forest on all {len(records)} records…")
        self.forest = self._forest().fit(X, y)
        self.n_records = len(records)
        return self

    def weight(self, student_id: str) -> tuple[int, float]:
        n, _ = self.offsets.get(student_id, (0, 0.0))
        k = self.k or 0.0
        return n, (n / (n + k) if (n + k) > 0 else 0.0)

    @property
    def uses_category(self) -> bool:
        """The fitted model has category columns. A model saved before 16 Oct 2026 has no such
        attribute: it was trained without categories."""
        return getattr(self, "category_used", False)

    def is_trusted(self, student_id: str) -> bool:
        """The gate is open for this student (always True with the gate switched off)."""
        if not self.gate:
            return True
        trust = self.trust.get(student_id)
        return trust is not None and trust.trusted

    def predict(self, records: Sequence[Mapping[str, Any]]) -> list[DriftPrediction]:
        if self.forest is None:
            raise RuntimeError("DriftModel is not trained")
        if not records:
            return []
        X = features(records, self.uses_category)
        point = self.forest.predict(X, quantiles=self.point_quantile)
        low, high = np.asarray(self.forest.predict(X, quantiles=list(self.quantiles))).T
        out = []
        for r, p, lo, hi in zip(records, point, low, high):
            n, w = self.weight(r["studentId"])
            shift = w * self.offsets.get(r["studentId"], (0, 0.0))[1]
            p, lo, hi = float(p + shift), float(lo + shift), float(hi + shift)
            if self.is_trusted(r["studentId"]):
                out.append(DriftPrediction(p, lo, hi, n, w))
            else:  # gate closed: the student's own estimate, range widened to contain it
                out.append(DriftPrediction(0.0, min(lo, 0.0), max(hi, 0.0), n, w, trusted=False))
        return out

    def predict_log(self, records: Sequence[Mapping[str, Any]]) -> np.ndarray:
        return np.array([p.log_point for p in self.predict(records)])

    def predict_interval(self, records: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
        preds = self.predict(records)
        return np.array([p.log_low for p in preds]), np.array([p.log_high for p in preds])
