"""Pydantic schemas for the knowledge API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import KnowledgeDocumentStatus


class KnowledgeDocumentCreate(BaseModel):
    number_document: str = Field(min_length=1, max_length=500)
    content: str = Field(min_length=1)
    source: str | None = Field(default=None, max_length=2048)

    @field_validator("number_document")
    @classmethod
    def strip_number_document(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("number_document must not be blank")
        return value


class KnowledgeDocumentCreated(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number_document: str
    source: str | None
    status: KnowledgeDocumentStatus
    created_at: datetime


class KnowledgeDocumentListItem(KnowledgeDocumentCreated):
    updated_at: datetime
    chunk_count: int
    indexing_error: str | None


class KnowledgeDocumentList(BaseModel):
    items: list[KnowledgeDocumentListItem]
    total: int
