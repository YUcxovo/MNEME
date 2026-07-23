"""Index unresolved citation targets for later local resolution.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-23
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Support resolution lookups by external target identity."""
    op.create_index(
        "ix_citations_external_target_id",
        "citations",
        ["external_target_id"],
    )


def downgrade() -> None:
    """Remove the external-target resolution index."""
    op.drop_index("ix_citations_external_target_id", table_name="citations")
