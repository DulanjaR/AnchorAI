"""C1's own settings. Team-wide settings (API key, database URL) come from
shared.config; this class holds only what is specific to C1.

Environment variables use the prefix C1_, e.g. C1_API_PREFIX=/c1/api.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class C1Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="C1_", env_file=".env", extra="ignore")

    # Base path of every C1 endpoint except /health. The one place it is defined
    # (open question: the base path for orchestration, CLAUDE.md §6 Q7).
    api_prefix: str = "/api"

    # Trained ML Model 1 file (ml/drift/persist.py), e.g. a c1_drift_model.joblib made in
    # notebooks/01. Empty or missing file → drift 1.0 (NoDrift), the approved fallback.
    drift_model_path: str = ""

    # Folder with the CESAW files (or CESAW_task_fact.csv itself), kept OUTSIDE the repository:
    # the licence is not stated, so the data is never committed (ml/drift/external/cesaw.py).
    cesaw_path: str = ""


c1_settings = C1Settings()
