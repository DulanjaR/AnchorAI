from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://anchor:anchor@localhost:5432/anchor"
    api_key: str = "change-me"
    llm_base_model: str = ""
    llm_adapter_path: str = ""


settings = Settings()
