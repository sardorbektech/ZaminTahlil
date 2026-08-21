from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "ZaminTahlil"
    app_env: Literal["demo", "prod"] = "demo"
    database_path: Path = Path("data/zamintahlil.sqlite3")
    artifact_dir: Path = Path("data/artifacts")
    cloud_free_threshold: float = Field(default=20.0, ge=0, le=100)
    sentinel_hub_client_id: str | None = None
    sentinel_hub_client_secret: str | None = None
    sentinel_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    sentinel_proxy: str | None = None
    openai_api_key: str | None = None
    openai_timeout_seconds: float = Field(default=45.0, gt=0, le=120)
    openai_primary_model: str = "gpt-5.4-nano"
    openai_fallback_model: str = "gpt-5.4-mini"
    cors_origins: str = ""
    models_dir: Path = Path("models")
    rag_similarity_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    rag_model_name: str = "nomic-ai/nomic-embed-text-v1.5"

    @field_validator("sentinel_proxy", mode="before")
    @classmethod
    def _empty_proxy_to_none(cls, value: object) -> object:
        # .env da SENTINEL_PROXY= bo'sh qoldirilganda pydantic uni '' deb
        # o'qiydi; httpx esa bo'sh proxy ni xato deb hisoblaydi.
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
