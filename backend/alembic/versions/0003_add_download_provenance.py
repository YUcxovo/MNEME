"""Add source download provenance to paper revisions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Track the size and completion time of each downloaded source PDF."""
    op.add_column("paper_versions", sa.Column("source_size_bytes", sa.BigInteger(), nullable=True))
    op.add_column(
        "paper_versions", sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_paper_versions_source_size_non_negative",
        "paper_versions",
        "source_size_bytes IS NULL OR source_size_bytes >= 0",
    )
    op.create_check_constraint(
        "ck_paper_versions_source_metadata_complete",
        "paper_versions",
        "(source_checksum IS NULL AND source_size_bytes IS NULL AND downloaded_at IS NULL) OR "
        "(source_checksum IS NOT NULL AND source_size_bytes IS NOT NULL "
        "AND downloaded_at IS NOT NULL)",
    )


def downgrade() -> None:
    """Remove source download provenance fields."""
    op.drop_constraint(
        "ck_paper_versions_source_metadata_complete", "paper_versions", type_="check"
    )
    op.drop_constraint(
        "ck_paper_versions_source_size_non_negative", "paper_versions", type_="check"
    )
    op.drop_column("paper_versions", "downloaded_at")
    op.drop_column("paper_versions", "source_size_bytes")
