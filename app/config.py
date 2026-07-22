from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ZaminTahlil"
    database_path: Path = Path("data/zamintahlil.sqlite3")
    artifact_dir: Path = Path("data/artifacts")
    cloud_free_threshold: float = Field(default=20.0, ge=0, le=100)
    sentinel_hub_client_id: str | None = None
    sentinel_hub_client_secret: str | None = None
    sentinel_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    openai_api_key: str | None = None
    openai_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    openai_primary_model: str = "gpt-5.4-nano"
    openai_fallback_model: str = "gpt-5.4-mini"


@lru_cache
def get_settings() -> Settings:
    return Settings()


cors_origins: list[str] = [
    "http://localhost:5173"
]  # dev uchun, keyin Lovable/prod domenlarni qo'shasiz
