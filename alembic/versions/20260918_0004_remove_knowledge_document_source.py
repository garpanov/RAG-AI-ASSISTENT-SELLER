"""Remove the knowledge document source column.

Revision ID: 20260918_0004
Revises: 20260918_0003
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0004"
down_revision: str | None = "20260918_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the unused source column."""

    op.drop_column("knowledge_documents", "source")


def downgrade() -> None:
    """Restore the optional source column."""

    op.add_column(
        "knowledge_documents",
        sa.Column("source", sa.String(length=2048), nullable=True),
    )
