"""ML Model 1 as the MVD service's DriftCorrector hook (app/services/planning.py).

Graceful fallback (CLAUDE.md §3.6): no model, an untrained model, or any error
while predicting → drift = 1.0 (the user's estimate), source 'fallback'. The
engine keeps working either way. Earned-trust gate closed for the student (16 Oct
2026) → drift 1.0 too, source 'gate' (the range stays, widened to contain the estimate).
"""
import logging
from pathlib import Path
from typing import Any, Mapping

from components.c1_disruption.app.services.planning import Correction, DriftCorrector, NoDrift
from components.c1_disruption.engine.time import to_minutes
from components.c1_disruption.ml.drift.model import DriftModel

log = logging.getLogger(__name__)


class ModelCorrector:
    def __init__(self, model: DriftModel | None, meta: Mapping[str, Any] | None = None) -> None:
        self.model = model
        self.meta = dict(meta or {})  # from persist.load_model: training date, dataset, k, …

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
            "category": task.get("category"),
        }
        try:
            (pred,) = self.model.predict([query])
        except Exception:  # never let the ML layer break planning
            log.exception("Drift model failed; falling back to drift 1.0")
            return Correction(hours, hours, hours, "fallback")
        point, low, high = (m / 60 for m in pred.corrected_minutes(hours * 60))
        if not pred.trusted:  # earned-trust gate closed: the student's own estimate
            return Correction(hours, min(low, hours), max(high, hours), "gate")
        # Keep low ≤ point ≤ high for the engine (quantiles of a forest can cross the mean).
        return Correction(point, min(low, point), max(high, point), "model")


def load_corrector(path: str | Path | None) -> DriftCorrector:
    """The DriftCorrector for a saved model file (C1_DRIFT_MODEL_PATH).

    Empty setting, missing file, or a file that cannot be loaded → NoDrift (drift 1.0),
    so the API always starts and plans with the approved fallback.
    """
    if not path:
        return NoDrift()
    from components.c1_disruption.ml.drift.persist import load_model

    try:
        model, meta = load_model(path)
    except FileNotFoundError:
        log.warning("Drift model %s not found; using drift 1.0", path)
        return NoDrift()
    except Exception:
        log.exception("Drift model %s could not be loaded; using drift 1.0", path)
        return NoDrift()
    if not meta["librariesMatch"]:
        log.warning("Drift model %s was saved with %s, running %s", path, meta.get("libraries"), meta["librariesNow"])
    log.info("Drift model loaded: %s records, dataset %s, trained %s", meta["records"], meta["dataset"], meta["trainedAt"])
    return ModelCorrector(model, meta)
