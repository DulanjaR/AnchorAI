"""The two ML hooks of the MVD service, with defaults that keep the approved
behaviour (methodology update, 14 Oct 2026).

  DriftCorrector   ML Model 1: corrected duration (point / low / high) per task.
                   Default NoDrift: drift = 1.0, corrected = the user's estimate.
  StrategyChooser  ML Model 2: which strategy configs to show, in which order.
                   Default FixedOrder over STRATEGIES (policy mode 'fixed_order').

Whatever they return is logged on the MVD record, so the metrics can compare
model on / off and the ranking shown (docs/METHODOLOGY.md §6).
"""
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from components.c1_disruption.engine import config as engine_config

# Strategy catalogue: id → engine strategy config (engine/strategy.py). Model 2
# extends this; the first entry is the approved default behaviour.
STRATEGIES: dict[str, dict[str, Any]] = {
    "default": {"compressRatio": engine_config.MAX_COMPRESSION},  # approved: up to 50%
    "compress_25": {"compressRatio": 0.25},  # shorten less, move more
    "no_compress": {"compressRatio": 0.0},  # never shorten: keep in full or move
    "deadline_first": {"compressRatio": engine_config.MAX_COMPRESSION, "deferOrder": "deadline"},
    "evening_first": {"compressRatio": engine_config.MAX_COMPRESSION, "recoveryTiming": "latest"},
}

POLICY_MODES = ("fixed_order", "bandit", "randomised")


@dataclass(frozen=True)
class Correction:
    point_hours: float
    low_hours: float
    high_hours: float
    source: str  # 'model' or 'fallback'


@dataclass(frozen=True)
class Ranking:
    policy_mode: str  # one of POLICY_MODES
    ranking: list[str]  # strategy ids, best first; ranking[0] shapes the MVD
    shown_policy: str = ""  # for 'randomised': which ranking was shown ('bandit' / 'fixed_order')
    features: list[float] = field(default_factory=list)  # Model 2 context vector (logged)


class DriftCorrector(Protocol):
    @property
    def model_on(self) -> bool: ...

    def correct(self, user_id: str, task: Mapping[str, Any], context: Mapping[str, Any]) -> Correction: ...


class StrategyChooser(Protocol):
    def rank(self, user_id: str, context: Mapping[str, Any]) -> Ranking:
        """context: date, planFrom, disruption, tasks, engineInput (without strategy), severity."""


class NoDrift:
    """ML Model 1 fallback: drift = 1.0 (CLAUDE.md §3.6)."""

    model_on = False

    def correct(self, user_id: str, task: Mapping[str, Any], context: Mapping[str, Any]) -> Correction:
        hours = task["estimatedHours"]
        return Correction(hours, hours, hours, "fallback")


@dataclass
class FixedOrder:
    """ML Model 2 baseline and pilot week 1: always the catalogue order."""

    order: list[str] = field(default_factory=lambda: list(STRATEGIES))

    def rank(self, user_id: str, context: Mapping[str, Any]) -> Ranking:
        return Ranking(policy_mode="fixed_order", ranking=list(self.order), shown_policy="fixed_order")


def reward(action: str, tags_changed: int = 0, total_tags: int = 0) -> float:
    """Model 2 reward (PROPOSED, owner to confirm): Accept = 1 · Reject = 0 ·
    Edit = 1 − (tags changed ÷ total tags)."""
    if action == "accept":
        return 1.0
    if action == "reject":
        return 0.0
    if action == "edit":
        return 1.0 - (tags_changed / total_tags if total_tags else 0.0)
    raise ValueError(f"Unknown decision '{action}'")


def learns(chooser: object) -> bool:
    """Choosers that learn from decisions (Model 2) have learn(user, features, strategy, reward)."""
    return callable(getattr(chooser, "learn", None))
