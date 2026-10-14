"""Pooled LinUCB with a shared and a per-student component (docs/METHODOLOGY.md §4).

For action a and student s the expected reward is   xᵀ(θ_a + δ_{s,a})
  θ_a      shared part, ridge regression on every student's events (penalty λ_shared)
  δ_{s,a}  student part, ridge on that student's residuals r − xᵀθ_a (penalty λ_student,
           larger, so it grows only with the student's own evidence; 0 for a new student)
Score = estimate + α · sqrt(xᵀA_a⁻¹x + xᵀB_{s,a}⁻¹x)   (optimism under uncertainty).
The ranking is the actions sorted by score; ties keep the catalogue order.
"""
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from components.c1_disruption.ml.bandit import settings


@dataclass
class _Ridge:
    dim: int
    penalty: float
    A: np.ndarray = field(init=False)
    b: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.A = self.penalty * np.eye(self.dim)
        self.b = np.zeros(self.dim)

    def coef(self) -> np.ndarray:
        return np.linalg.solve(self.A, self.b)

    def width(self, x: np.ndarray) -> float:
        return float(x @ np.linalg.solve(self.A, x))

    def add(self, x: np.ndarray, target: float) -> None:
        self.A += np.outer(x, x)
        self.b += target * x


class PooledLinUCB:
    def __init__(
        self,
        actions: Sequence[str],
        dim: int,
        alpha: float = settings.ALPHA,
        lambda_shared: float = settings.LAMBDA_SHARED,
        lambda_student: float = settings.LAMBDA_STUDENT,
    ) -> None:
        self.actions = list(actions)
        self.dim = dim
        self.alpha = alpha
        self.lambda_student = lambda_student
        self.shared = {a: _Ridge(dim, lambda_shared) for a in self.actions}
        self.students: dict[tuple[str, str], _Ridge] = {}

    def _student(self, student: str, action: str) -> _Ridge:
        key = (student, action)
        if key not in self.students:
            self.students[key] = _Ridge(self.dim, self.lambda_student)
        return self.students[key]

    def scores(self, student: str, x: np.ndarray) -> dict[str, float]:
        out = {}
        for a in self.actions:
            shared, own = self.shared[a], self._student(student, a)
            estimate = x @ shared.coef() + x @ own.coef()
            out[a] = float(estimate + self.alpha * np.sqrt(shared.width(x) + own.width(x)))
        return out

    def rank(self, student: str, x: np.ndarray) -> list[str]:
        scores = self.scores(student, x)
        return sorted(self.actions, key=lambda a: (-scores[a], self.actions.index(a)))

    def update(self, student: str, x: np.ndarray, action: str, reward: float) -> None:
        shared = self.shared[action]
        residual = reward - float(x @ shared.coef())  # before the shared update
        shared.add(x, reward)
        self._student(student, action).add(x, residual)
