"""ML Model 1 as the MVD service's DriftCorrector hook (app/services/planning.py).

Graceful fallback (CLAUDE.md §3.6): no model, an untrained model, or any error
while predicting → drift = 1.0 (the user's estimate), source 'fallback'. The
engine keeps working either way.
"""
import logging
from typing import Any, Mapping

from components.c1_disruption.app.services.planning import Correction
from components.c1_disruption.engine.time import to_minutes
from components.c1_disruption.ml.drift.model import DriftModel

log = logging.getLogger(__name__)


class ModelCorrector:
    def __init__(self, model: DriftModel | None) -> None:
        self.model = model

    @property
    def model_on(self) -> bool:
        return self.model is not None and self.model.trained

    def correct(self, user_id: str, task: Mapping[str, Any], context: Mapping[str, Any]) -> Correction:
        hours = task["estimatedHours"]
        if not self.model_on:
            return Correction(hours, hours, hours, "fallback")
        start = task.get("plannedStart") or context.get("planFrom") or "09:00"
        query = {
            "studentId": user_id,
            "taskType": task["type"],
            "priority": task["priority"],
            "estimatedMinutes": hours * 60,
            "date": context["date"],
            "startHour": to_minutes(start) // 60,
        }
        try:
            (pred,) = self.model.predict([query])
        except Exception:  # never let the ML layer break planning
            log.exception("Drift model failed; falling back to drift 1.0")
            return Correction(hours, hours, hours, "fallback")
        point, low, high = (m / 60 for m in pred.corrected_minutes(hours * 60))
        # Keep low ≤ point ≤ high for the engine (quantiles of a forest can cross the mean).
        return Correction(point, min(low, point), max(high, point), "model")
