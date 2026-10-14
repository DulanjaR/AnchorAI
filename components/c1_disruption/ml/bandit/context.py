"""Model 2 context features (docs/METHODOLOGY.md §4).

  bias · kind (environment / unavailable) · severity · time-of-day bucket
  (morning / afternoon / evening) · share of digital tasks · slack ratio ·
  weekend · student history (past acceptance rate, number of past events)
"""
import math
from datetime import date as Date
from typing import Any, Mapping, Sequence

import numpy as np

from components.c1_disruption.engine import config as engine_config
from components.c1_disruption.engine.overload import check_overload
from components.c1_disruption.engine.time import to_minutes
from components.c1_disruption.ml.bandit import settings

FEATURE_NAMES = (
    "bias", "kind_unavailable", "severity", "morning", "afternoon", "evening",
    "digital_share", "slack_ratio", "weekend", "past_acceptance", "past_events",
)


def slack_ratio(engine_input: Mapping[str, Any]) -> float:
    """Slack of the day being replanned (engine/overload.py), clipped to [-1, 1]."""
    report = check_overload({k: v for k, v in engine_input.items() if k not in ("disruption", "strategy")})
    ratio = report["slackRatio"]
    return -1.0 if ratio is None else max(-1.0, min(1.0, ratio))


def features(
    engine_input: Mapping[str, Any], severity: int, past_rewards: Sequence[float] = ()
) -> np.ndarray:
    """Context vector in FEATURE_NAMES order for one disruption event."""
    tasks = engine_input.get("tasks") or []
    hour = to_minutes(engine_input.get("planFrom") or engine_input["workHours"]["start"]) // 60
    kind = engine_config.DISRUPTION_KINDS[engine_input["disruption"]["type"]]
    acceptance = float(np.mean(past_rewards)) if past_rewards else settings.PRIOR_ACCEPTANCE
    return np.array([
        1.0,
        1.0 if kind == "unavailable" else 0.0,
        (severity - 1) / 2,  # 1–3 → 0–1
        1.0 if hour < settings.MORNING_BEFORE else 0.0,
        1.0 if settings.MORNING_BEFORE <= hour < settings.AFTERNOON_BEFORE else 0.0,
        1.0 if hour >= settings.AFTERNOON_BEFORE else 0.0,
        sum(t["type"] == "Digital" for t in tasks) / len(tasks) if tasks else 0.0,
        slack_ratio(engine_input),
        1.0 if Date.fromisoformat(engine_input["date"]).weekday() >= 5 else 0.0,
        acceptance,
        math.log1p(len(past_rewards)) / math.log1p(20),  # ≈ 1 after 20 events
    ])
