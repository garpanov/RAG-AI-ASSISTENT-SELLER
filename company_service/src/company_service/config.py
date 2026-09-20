"""Environment-based configuration for the standalone service."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    orders_api_key: str
    webhook_secret: str


@lru_cache
def get_settings() -> Settings:
    return Settings.model_validate({})

