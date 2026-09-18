"""Add a monotonic revision to knowledge documents.

Revision ID: 20260918_0005
Revises: 20260918_0004
Create Date: 2026-09-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0005"
down_revision: str | None = "20260918_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the initial revision to existing and new documents."""

    op.add_column(
        "knowledge_documents",
        sa.Column(
            "revision",
            sa.BigInteger(),
            server_default="1",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Remove the document revision."""

    op.drop_column("knowledge_documents", "revision")
