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


c1_settings = C1Settings()
