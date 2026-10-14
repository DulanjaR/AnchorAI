"""Save and load a trained ML Model 1 (e.g. trained in Colab, used by the API).

    save_model(model, "c1_drift_model.joblib", dataset="SYNTHETIC")
      → c1_drift_model.joblib       the fitted DriftModel (joblib)
      → c1_drift_model.joblib.json  metadata: format version, training date, record
                                    count, dataset flag, k, quantiles, library versions
    model, meta = load_model("c1_drift_model.joblib")

The .joblib file is a pickle: load only files you made yourself (the notebook).
Model files are never committed (components/c1_disruption/.gitignore).
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy
import quantile_forest
import sklearn

from components.c1_disruption.ml.drift.model import DriftModel

FORMAT_VERSION = 1


def metadata_path(model_path: str | Path) -> Path:
    path = Path(model_path)
    return path.with_name(path.name + ".json")


def _versions() -> dict[str, str]:
    return {"numpy": numpy.__version__, "scikit-learn": sklearn.__version__, "quantile-forest": quantile_forest.__version__}


def save_model(model: DriftModel, path: str | Path, dataset: str) -> dict[str, Any]:
    """Writes the model and its metadata; returns the metadata. `dataset` says what it
    was trained on, e.g. 'SYNTHETIC' (CLAUDE.md rule 6) or 'PILOT'."""
    if not model.trained:
        raise ValueError("Only a trained DriftModel can be saved")
    path = Path(path)
    meta = {
        "format": FORMAT_VERSION,
        "model": "C1 ML Model 1 (pooled quantile forest + per-student shrinkage)",
        "trainedAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "records": model.n_records,
        "students": len(model.offsets),
        "dataset": dataset,
        "synthetic": dataset == "SYNTHETIC",
        "k": model.k,
        "quantiles": list(model.quantiles),
        "libraries": _versions(),
    }
    joblib.dump(model, path)
    metadata_path(path).write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def load_model(path: str | Path) -> tuple[DriftModel, dict[str, Any]]:
    """Loads a model saved by save_model. Raises FileNotFoundError if either file is
    missing and ValueError if it is not a trained C1 drift model of a known format."""
    path = Path(path)
    meta_file = metadata_path(path)
    if not path.is_file() or not meta_file.is_file():
        raise FileNotFoundError(f"Drift model files not found: {path} and {meta_file.name}")
    meta = json.loads(meta_file.read_text(encoding="utf-8"))
    if meta.get("format") != FORMAT_VERSION:
        raise ValueError(f"Unknown drift model format {meta.get('format')!r} (expected {FORMAT_VERSION})")
    model = joblib.load(path)
    if not isinstance(model, DriftModel) or not model.trained:
        raise ValueError(f"{path.name} is not a trained C1 drift model")
    meta["librariesNow"] = _versions()
    meta["librariesMatch"] = meta["librariesNow"] == meta.get("libraries")
    return model, meta
