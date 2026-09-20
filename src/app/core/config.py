"""Environment-based application settings."""

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import BeforeValidator
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
    rabbitmq_url: str
    knowledge_queue_name: str
    message_queue_name: str

    embedding_provider: str
    embedding_model_name: str
    embedding_dimensions: Annotated[Literal[384], BeforeValidator(int)]
    embedding_batch_size: int

    knowledge_chunk_size: int
    knowledge_chunk_overlap: int

    planner_provider: str
    planner_base_url: str
    planner_api_key: str
    planner_model_name: str
    planner_timeout_seconds: float
    planner_handoff_confidence_threshold: int

    rag_candidate_k: int
    rag_top_k: int
    reranker_provider: str
    reranker_model_name: str

    answer_provider: str
    answer_base_url: str
    answer_api_key: str
    answer_model_name: str
    answer_timeout_seconds: float

    orders_base_url: str
    orders_api_key: str
    company_webhook_url: str
    company_webhook_secret: str
    integration_timeout_seconds: float


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-in-practice settings instance per process."""

    return Settings.model_validate({})
