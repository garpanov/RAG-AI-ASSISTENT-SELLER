"""Add knowledge document indexing state.

Revision ID: 20260917_0002
Revises: 20260916_0001
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260917_0002"
down_revision: str | None = "20260916_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add state used by the asynchronous knowledge indexing worker."""

    op.add_column(
        "knowledge_documents",
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="pending",
            nullable=False,
        ),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("indexing_error", sa.Text(), nullable=True),
    )
    op.create_check_constraint(
        "knowledge_document_status",
        "knowledge_documents",
        "status IN ('pending', 'processing', 'ready', 'failed')",
    )
    op.create_index(
        "ix_knowledge_documents_status",
        "knowledge_documents",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    """Remove knowledge document indexing state."""

    op.drop_index(
        "ix_knowledge_documents_status", table_name="knowledge_documents"
    )
    op.drop_constraint(
        "ck_knowledge_documents_knowledge_document_status",
        "knowledge_documents",
        type_="check",
    )
    op.drop_column("knowledge_documents", "indexing_error")
    op.drop_column("knowledge_documents", "status")
