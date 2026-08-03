"""Add citation-resolution state and model-call accounting to QA messages.

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "qa_messages",
        sa.Column("citation_resolution", sa.String(length=20), nullable=True),
    )
    op.add_column("qa_messages", sa.Column("model_calls", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "qa_citation_resolution",
        "qa_messages",
        "citation_resolution IS NULL OR citation_resolution IN "
        "('verified', 'corrected', 'unresolved', 'not_applicable')",
    )
    op.create_check_constraint(
        "ck_qa_messages_model_calls_non_negative",
        "qa_messages",
        "model_calls IS NULL OR model_calls >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_qa_messages_model_calls_non_negative", "qa_messages", type_="check")
    op.drop_constraint("qa_citation_resolution", "qa_messages", type_="check")
    op.drop_column("qa_messages", "model_calls")
    op.drop_column("qa_messages", "citation_resolution")
