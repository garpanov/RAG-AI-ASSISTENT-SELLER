"""Rename document title and make document number unique.

Revision ID: 20260918_0003
Revises: 20260917_0002
Create Date: 2026-09-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260918_0003"
down_revision: str | None = "20260917_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename title to number_document and enforce uniqueness."""

    op.alter_column(
        "knowledge_documents",
        "title",
        new_column_name="number_document",
    )
    op.create_unique_constraint(
        "uq_knowledge_documents_number_document",
        "knowledge_documents",
        ["number_document"],
    )


def downgrade() -> None:
    """Restore the non-unique title column."""

    op.drop_constraint(
        "uq_knowledge_documents_number_document",
        "knowledge_documents",
        type_="unique",
    )
    op.alter_column(
        "knowledge_documents",
        "number_document",
        new_column_name="title",
    )
