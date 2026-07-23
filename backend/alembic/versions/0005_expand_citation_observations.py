"""Expand citations to represent incoming external observations.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Store Semantic Scholar identities and bidirectional citation edges."""
    op.add_column(
        "papers",
        sa.Column("semantic_scholar_id", sa.String(length=128), nullable=True),
    )
    op.create_unique_constraint(
        "uq_papers_semantic_scholar_id",
        "papers",
        ["semantic_scholar_id"],
    )

    op.add_column(
        "citations",
        sa.Column("external_source_id", sa.String(length=200), nullable=True),
    )
    op.alter_column("citations", "source_paper_id", existing_type=sa.UUID(), nullable=True)
    op.drop_constraint("ck_citations_has_target", "citations", type_="check")
    op.drop_constraint("ck_citations_no_self_edge", "citations", type_="check")
    op.drop_index("uq_citations_external_edge", table_name="citations")
    op.drop_index("uq_citations_internal_edge", table_name="citations")

    # The M1 constraint allowed both target identities. Prefer the already
    # resolved local paper before tightening the invariant to exactly one.
    op.execute(
        "UPDATE citations SET external_target_id = NULL "
        "WHERE target_paper_id IS NOT NULL AND external_target_id IS NOT NULL"
    )

    op.create_check_constraint(
        "ck_citations_one_source",
        "citations",
        "(source_paper_id IS NOT NULL AND external_source_id IS NULL) OR "
        "(source_paper_id IS NULL AND external_source_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_citations_one_target",
        "citations",
        "(target_paper_id IS NOT NULL AND external_target_id IS NULL) OR "
        "(target_paper_id IS NULL AND external_target_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_citations_has_local_endpoint",
        "citations",
        "source_paper_id IS NOT NULL OR target_paper_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_citations_no_self_edge",
        "citations",
        "source_paper_id IS NULL OR target_paper_id IS NULL OR source_paper_id <> target_paper_id",
    )
    op.create_index(
        "uq_citations_internal_edge",
        "citations",
        ["source_paper_id", "target_paper_id"],
        unique=True,
        postgresql_where=sa.text("source_paper_id IS NOT NULL AND target_paper_id IS NOT NULL"),
    )
    op.create_index(
        "uq_citations_external_target_edge",
        "citations",
        ["source_paper_id", "external_target_id"],
        unique=True,
        postgresql_where=sa.text("source_paper_id IS NOT NULL AND external_target_id IS NOT NULL"),
    )
    op.create_index(
        "uq_citations_external_source_edge",
        "citations",
        ["external_source_id", "target_paper_id"],
        unique=True,
        postgresql_where=sa.text("external_source_id IS NOT NULL AND target_paper_id IS NOT NULL"),
    )
    op.create_index(
        "ix_citations_target_paper_id",
        "citations",
        ["target_paper_id"],
    )


def downgrade() -> None:
    """Return to outbound-only citations, dropping unrepresentable incoming rows."""
    op.drop_index("ix_citations_target_paper_id", table_name="citations")
    op.drop_index("uq_citations_external_source_edge", table_name="citations")
    op.drop_index("uq_citations_external_target_edge", table_name="citations")
    op.drop_index("uq_citations_internal_edge", table_name="citations")
    op.drop_constraint("ck_citations_no_self_edge", "citations", type_="check")
    op.drop_constraint("ck_citations_has_local_endpoint", "citations", type_="check")
    op.drop_constraint("ck_citations_one_target", "citations", type_="check")
    op.drop_constraint("ck_citations_one_source", "citations", type_="check")

    op.execute("DELETE FROM citations WHERE source_paper_id IS NULL")
    op.alter_column("citations", "source_paper_id", existing_type=sa.UUID(), nullable=False)
    op.create_check_constraint(
        "ck_citations_has_target",
        "citations",
        "target_paper_id IS NOT NULL OR external_target_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_citations_no_self_edge",
        "citations",
        "target_paper_id IS NULL OR target_paper_id <> source_paper_id",
    )
    op.create_index(
        "uq_citations_internal_edge",
        "citations",
        ["source_paper_id", "target_paper_id"],
        unique=True,
        postgresql_where=sa.text("target_paper_id IS NOT NULL"),
    )
    op.create_index(
        "uq_citations_external_edge",
        "citations",
        ["source_paper_id", "external_target_id"],
        unique=True,
        postgresql_where=sa.text("external_target_id IS NOT NULL"),
    )
    op.drop_column("citations", "external_source_id")

    op.drop_constraint("uq_papers_semantic_scholar_id", "papers", type_="unique")
    op.drop_column("papers", "semantic_scholar_id")
