"""Add revision-scoped document provenance and pipeline identity.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Track parse provenance and bind paper jobs to one exact revision."""
    op.add_column(
        "paper_versions", sa.Column("parsed_checksum", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "paper_versions", sa.Column("parser_version", sa.String(length=64), nullable=True)
    )
    op.add_column("paper_versions", sa.Column("parse_quality", sa.String(length=32), nullable=True))
    op.add_column(
        "paper_versions", sa.Column("parsed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_check_constraint(
        "ck_paper_versions_source_checksum_sha256",
        "paper_versions",
        "source_checksum IS NULL OR length(source_checksum) = 64",
    )
    op.create_check_constraint(
        "ck_paper_versions_parsed_checksum_sha256",
        "paper_versions",
        "parsed_checksum IS NULL OR length(parsed_checksum) = 64",
    )
    op.create_check_constraint(
        "parse_quality",
        "paper_versions",
        "parse_quality IN ('structured', 'text_only', 'abstract_only')",
    )
    op.create_check_constraint(
        "ck_paper_versions_parse_metadata_complete",
        "paper_versions",
        "(parsed_checksum IS NULL AND parser_version IS NULL "
        "AND parse_quality IS NULL AND parsed_at IS NULL) OR "
        "(parsed_checksum IS NOT NULL AND parser_version IS NOT NULL "
        "AND parse_quality IS NOT NULL AND parsed_at IS NOT NULL)",
    )

    op.add_column(
        "pipeline_jobs",
        sa.Column("paper_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_check_constraint(
        "ck_pipeline_jobs_version_requires_paper",
        "pipeline_jobs",
        "paper_version_id IS NULL OR paper_id IS NOT NULL",
    )
    op.create_foreign_key(
        "fk_pipeline_jobs_version_paper",
        "pipeline_jobs",
        "paper_versions",
        ["paper_version_id", "paper_id"],
        ["id", "paper_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_pipeline_jobs_version_status",
        "pipeline_jobs",
        ["paper_version_id", "status"],
    )


def downgrade() -> None:
    """Remove document provenance while preserving the v0.1 schema."""
    op.drop_index("ix_pipeline_jobs_version_status", table_name="pipeline_jobs")
    op.drop_constraint("fk_pipeline_jobs_version_paper", "pipeline_jobs", type_="foreignkey")
    op.drop_constraint("ck_pipeline_jobs_version_requires_paper", "pipeline_jobs", type_="check")
    op.drop_column("pipeline_jobs", "paper_version_id")

    op.drop_constraint("ck_paper_versions_parse_metadata_complete", "paper_versions", type_="check")
    op.drop_constraint("parse_quality", "paper_versions", type_="check")
    op.drop_constraint("ck_paper_versions_parsed_checksum_sha256", "paper_versions", type_="check")
    op.drop_constraint("ck_paper_versions_source_checksum_sha256", "paper_versions", type_="check")
    op.drop_column("paper_versions", "parsed_at")
    op.drop_column("paper_versions", "parse_quality")
    op.drop_column("paper_versions", "parser_version")
    op.drop_column("paper_versions", "parsed_checksum")
