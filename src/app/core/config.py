"""Environment-based application settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    database_url: str
    rabbitmq_url: str = "amqp://guest:guest@localhost/"
    knowledge_queue_name: str = "knowledge.documents.index"

    embedding_provider: str = "qwen3"
    embedding_model_name: str = "Qwen/Qwen3-Embedding-0.6B"
    embedding_dimensions: Literal[384] = 384
    embedding_batch_size: int = 16

    knowledge_chunk_size: int = 1200
    knowledge_chunk_overlap: int = 200


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-in-practice settings instance per process."""

    return Settings.model_validate({})
