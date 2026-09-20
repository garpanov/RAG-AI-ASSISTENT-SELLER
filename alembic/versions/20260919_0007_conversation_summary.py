"""Add rolling conversation summary state.

Revision ID: 20260919_0007
Revises: 20260919_0006
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260919_0007"
down_revision: str | None = "20260919_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store a rolling summary and the last message included in it."""

    op.add_column(
        "conversations",
        sa.Column("summary", sa.Text(), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("summary_through_message_id", sa.Uuid(), nullable=True),
    )


def downgrade() -> None:
    """Remove rolling conversation summary state."""

    op.drop_column("conversations", "summary_through_message_id")
    op.drop_column("conversations", "summary")
