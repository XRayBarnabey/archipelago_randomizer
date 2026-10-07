from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    steam_api_key: str = ""
    database_url: str = "postgresql+psycopg://archipelago:archipelago@postgres:5432/archipelago"
    cors_origins: str = "http://localhost:8080"
    log_level: str = "INFO"
    steam_cache_duration: int = 3600
    archipelago_sync_enabled: bool = False
    http_timeout: float = 15.0
    environment: str = "production"

    @field_validator("database_url")
    @classmethod
    def _driver(cls, value: str) -> str:
        if value.startswith("postgresql://"):
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @field_validator("steam_cache_duration", mode="before")
    @classmethod
    def _empty_int(cls, value):
        return 3600 if value in ("", None) else value

    @field_validator("archipelago_sync_enabled", mode="before")
    @classmethod
    def _empty_bool(cls, value):
        return False if value in ("", None) else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
