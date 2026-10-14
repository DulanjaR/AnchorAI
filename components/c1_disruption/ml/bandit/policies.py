"""Model 2 reward, baselines, and the StrategyChooser used by the MVD service.

Reward (PROPOSED, owner to confirm): Accept = 1 · Reject = 0 ·
Edit = 1 − (tags changed ÷ total tags).

Policies all have rank(student, x) → action ids and update(student, x, action, reward):
  FixedOrderPolicy       the catalogue order (baseline; pilot week 1)
  MostAcceptedPolicy     per student, actions by mean reward so far (baseline)
  RandomPolicy           a seeded random order (baseline)
  PooledLinUCB           the bandit (linucb.py)
"""
import random
from collections import defaultdict
from typing import Any, Mapping, Sequence

import numpy as np

from components.c1_disruption.app.services.planning import Ranking, reward  # noqa: F401 (reward re-exported)
from components.c1_disruption.ml.bandit import settings
from components.c1_disruption.ml.bandit.actions import ACTIONS
from components.c1_disruption.ml.bandit.context import FEATURE_NAMES, features
from components.c1_disruption.ml.bandit.linucb import PooledLinUCB


class FixedOrderPolicy:
    def __init__(self, actions: Sequence[str]) -> None:
        self.actions = list(actions)

    def rank(self, student: str, x: np.ndarray) -> list[str]:
        return list(self.actions)

    def update(self, student: str, x: np.ndarray, action: str, value: float) -> None:
        pass


class MostAcceptedPolicy:
    """Per student: actions by mean reward so far; untried actions keep catalogue order after tried ones with mean ≥ 0.5."""

    def __init__(self, actions: Sequence[str]) -> None:
        self.actions = list(actions)
        self.history: dict[tuple[str, str], list[float]] = defaultdict(list)

    def rank(self, student: str, x: np.ndarray) -> list[str]:
        def mean(a: str) -> float:
            h = self.history[(student, a)]
            return float(np.mean(h)) if h else settings.PRIOR_ACCEPTANCE

        return sorted(self.actions, key=lambda a: (-mean(a), self.actions.index(a)))

    def update(self, student: str, x: np.ndarray, action: str, value: float) -> None:
        self.history[(student, action)].append(value)


class RandomPolicy:
    def __init__(self, actions: Sequence[str], seed: int = 0) -> None:
        self.actions = list(actions)
        self.rng = random.Random(seed)

    def rank(self, student: str, x: np.ndarray) -> list[str]:
        order = list(self.actions)
        self.rng.shuffle(order)
        return order

    def update(self, student: str, x: np.ndarray, action: str, value: float) -> None:
        pass


class BanditChooser:
    """StrategyChooser for the MVD service (app/services/planning.py).

    mode: fixed_order (default) · bandit · randomised (per event, show the bandit or
    the fixed ranking at random; the record logs which). learn() is called by the
    service after every decision, in every mode, so the bandit keeps learning even
    while the fixed order is shown (week 1).
    """

    def __init__(self, mode: str = settings.POLICY_MODE, seed: int = 0, actions: Sequence[str] | None = None) -> None:
        if mode not in ("fixed_order", "bandit", "randomised"):
            raise ValueError(f"Unknown policy mode '{mode}'")
        self.mode = mode
        self.actions = list(actions or ACTIONS)
        self.fixed = FixedOrderPolicy(self.actions)
        self.bandit = PooledLinUCB(self.actions, dim=len(FEATURE_NAMES))
        self.rng = random.Random(seed)
        self.rewards: dict[str, list[float]] = defaultdict(list)  # student history

    def context(self, user_id: str, context: Mapping[str, Any]) -> np.ndarray:
        return features(context["engineInput"], context["severity"], self.rewards[user_id])

    def rank(self, user_id: str, context: Mapping[str, Any]) -> Ranking:
        x = self.context(user_id, context)
        shown = self.mode
        if self.mode == "randomised":
            shown = "bandit" if self.rng.random() < settings.RANDOMISED_BANDIT_SHARE else "fixed_order"
        policy = self.bandit if shown == "bandit" else self.fixed
        return Ranking(policy_mode=self.mode, ranking=policy.rank(user_id, x), shown_policy=shown,
                       features=[float(v) for v in x])

    def learn(self, user_id: str, features: Sequence[float], strategy_id: str, value: float) -> None:
        self.bandit.update(user_id, np.array(features, dtype=float), strategy_id, value)
        self.rewards[user_id].append(value)
