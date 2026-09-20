"""Add asynchronous message processing state.

Revision ID: 20260919_0006
Revises: 20260918_0005
Create Date: 2026-09-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260919_0006"
down_revision: str | None = "20260918_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

message_processing_status = postgresql.ENUM(
    "pending",
    "processing",
    "completed",
    "failed",
    name="message_processing_status",
    create_type=False,
)


def upgrade() -> None:
    """Add state and planner diagnostics to customer messages."""

    message_processing_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "messages",
        sa.Column(
            "processing_status",
            message_processing_status,
            nullable=True,
        ),
    )
    op.add_column(
        "messages",
        sa.Column(
            "planner_result",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "messages",
        sa.Column("processing_error", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_messages_processing_status",
        "messages",
        ["processing_status"],
        unique=False,
    )


def downgrade() -> None:
    """Remove asynchronous message processing state."""

    op.drop_index("ix_messages_processing_status", table_name="messages")
    op.drop_column("messages", "processing_error")
    op.drop_column("messages", "planner_result")
    op.drop_column("messages", "processing_status")
    message_processing_status.drop(op.get_bind(), checkfirst=True)
