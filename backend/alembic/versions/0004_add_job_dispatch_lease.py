"""Add a recoverable dispatch lease to durable pipeline jobs.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Record when a queued job was last offered to ARQ."""
    op.add_column(
        "pipeline_jobs",
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_pipeline_jobs_dispatchable",
        "pipeline_jobs",
        ["status", "dispatched_at", "created_at"],
    )


def downgrade() -> None:
    """Remove the dispatch lease while preserving durable job state."""
    op.drop_index("ix_pipeline_jobs_dispatchable", table_name="pipeline_jobs")
    op.drop_column("pipeline_jobs", "dispatched_at")
