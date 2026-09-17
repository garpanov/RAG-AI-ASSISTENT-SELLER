"""Create the initial support platform schema.

Revision ID: 20260916_0001
Revises:
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260916_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

conversation_status = postgresql.ENUM(
    "bot",
    "waiting_manager",
    "manager",
    "closed",
    name="conversation_status",
    create_type=False,
)
message_author = postgresql.ENUM(
    "customer",
    "assistant",
    "manager",
    name="message_author",
    create_type=False,
)
handoff_status = postgresql.ENUM(
    "waiting",
    "claimed",
    "resolved",
    "cancelled",
    name="handoff_status",
    create_type=False,
)
api_key_role = postgresql.ENUM(
    "client",
    "manager",
    "admin",
    name="api_key_role",
    create_type=False,
)


def upgrade() -> None:
    """Create PostgreSQL types, tables, constraints, and indexes."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    bind = op.get_bind()
    conversation_status.create(bind, checkfirst=True)
    message_author.create(bind, checkfirst=True)
    handoff_status.create(bind, checkfirst=True)
    api_key_role.create(bind, checkfirst=True)

    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("customer_reference", sa.String(length=255), nullable=True),
        sa.Column(
            "status",
            conversation_status,
            server_default="bot",
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )
    op.create_index(
        "ix_conversations_status", "conversations", ["status"], unique=False
    )

    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("source", sa.String(length=2048), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_documents"),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("key_hash", sa.String(length=255), nullable=False),
        sa.Column("role", api_key_role, nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_api_keys"),
        sa.UniqueConstraint("key_hash", name="uq_api_keys_key_hash"),
    )
    op.create_index("ix_api_keys_role", "api_keys", ["role"], unique=False)

    op.create_table(
        "messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("author", message_author, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "source_references", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index(
        "ix_messages_conversation_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(dim=384), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="chunk_index_non_negative",
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="token_count_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            name="fk_knowledge_chunks_document_id_knowledge_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_knowledge_chunks"),
        sa.UniqueConstraint(
            "document_id",
            "chunk_index",
            name="uq_knowledge_chunks_document_id",
        ),
    )
    op.create_index(
        "ix_knowledge_chunks_document_id",
        "knowledge_chunks",
        ["document_id"],
        unique=False,
    )

    op.create_table(
        "handoffs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "status",
            handoff_status,
            server_default="waiting",
            nullable=False,
        ),
        sa.Column("assigned_manager_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["assigned_manager_id"],
            ["api_keys.id"],
            name="fk_handoffs_assigned_manager_id_api_keys",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_handoffs_conversation_id_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_handoffs"),
    )
    op.create_index(
        "ix_handoffs_assigned_manager_id",
        "handoffs",
        ["assigned_manager_id"],
        unique=False,
    )
    op.create_index(
        "ix_handoffs_conversation_id",
        "handoffs",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        "ix_handoffs_status_created_at",
        "handoffs",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the initial support platform schema."""

    op.drop_index("ix_handoffs_status_created_at", table_name="handoffs")
    op.drop_index("ix_handoffs_conversation_id", table_name="handoffs")
    op.drop_index("ix_handoffs_assigned_manager_id", table_name="handoffs")
    op.drop_table("handoffs")

    op.drop_index(
        "ix_knowledge_chunks_document_id", table_name="knowledge_chunks"
    )
    op.drop_table("knowledge_chunks")

    op.drop_index("ix_messages_conversation_created_at", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_api_keys_role", table_name="api_keys")
    op.drop_table("api_keys")
    op.drop_table("knowledge_documents")

    op.drop_index("ix_conversations_status", table_name="conversations")
    op.drop_table("conversations")

    bind = op.get_bind()
    api_key_role.drop(bind, checkfirst=True)
    handoff_status.drop(bind, checkfirst=True)
    message_author.drop(bind, checkfirst=True)
    conversation_status.drop(bind, checkfirst=True)

    op.execute("DROP EXTENSION IF EXISTS vector")
