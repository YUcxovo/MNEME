"""Create the v0.1 application schema.

Revision ID: 0001
Revises:
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIMENSIONS = 1536


def string_enum(*values: str, name: str) -> sa.Enum:
    """Build a portable string enum with an explicit check-constraint name."""
    return sa.Enum(
        *values,
        name=name,
        native_enum=False,
        create_constraint=True,
    )


def upgrade() -> None:
    """Create the complete v0.1 schema in foreign-key dependency order."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "authors",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("semantic_scholar_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_authors"),
        sa.UniqueConstraint("normalized_name", name="uq_authors_normalized_name"),
        sa.UniqueConstraint(
            "semantic_scholar_id",
            name="uq_authors_semantic_scholar_id",
        ),
    )

    op.create_table(
        "papers",
        sa.Column("arxiv_id", sa.String(length=64), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("abstract", sa.Text(), nullable=False),
        sa.Column("primary_category", sa.String(length=64), nullable=False),
        sa.Column("categories", postgresql.ARRAY(sa.String(length=64)), nullable=False),
        sa.Column("pdf_url", sa.Text(), nullable=False),
        sa.Column("source_license", sa.String(length=255), nullable=True),
        sa.Column(
            "processing_status",
            string_enum(
                "metadata_only",
                "queued",
                "processing",
                "ready",
                "partial",
                "failed",
                name="processing_status",
            ),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_papers"),
        sa.UniqueConstraint("arxiv_id", name="uq_papers_arxiv_id"),
    )
    op.create_index(
        "ix_papers_category_published",
        "papers",
        ["primary_category", "published_at", "id"],
    )
    op.create_index("ix_papers_published_id", "papers", ["published_at", "id"])

    op.create_table(
        "users",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )

    op.create_table(
        "citations",
        sa.Column("source_paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_paper_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("external_target_id", sa.String(length=200), nullable=True),
        sa.Column("algorithm_weight", sa.Float(), nullable=True),
        sa.Column("algorithm_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "target_paper_id IS NOT NULL OR external_target_id IS NOT NULL",
            name="ck_citations_has_target",
        ),
        sa.CheckConstraint(
            "target_paper_id IS NULL OR target_paper_id <> source_paper_id",
            name="ck_citations_no_self_edge",
        ),
        sa.ForeignKeyConstraint(
            ["source_paper_id"],
            ["papers.id"],
            name="fk_citations_source_paper_id_papers",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["target_paper_id"],
            ["papers.id"],
            name="fk_citations_target_paper_id_papers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_citations"),
    )
    op.create_index(
        "uq_citations_external_edge",
        "citations",
        ["source_paper_id", "external_target_id"],
        unique=True,
        postgresql_where=sa.text("external_target_id IS NOT NULL"),
    )
    op.create_index(
        "uq_citations_internal_edge",
        "citations",
        ["source_paper_id", "target_paper_id"],
        unique=True,
        postgresql_where=sa.text("target_paper_id IS NOT NULL"),
    )

    op.create_table(
        "digests",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "digest_type",
            string_enum("weekly", "manual", name="digest_type"),
            nullable=False,
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("preference_model_version", sa.Integer(), nullable=False),
        sa.Column("generator_version", sa.String(length=100), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "preference_model_version > 0",
            name="ck_digests_preference_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_digests_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_digests"),
    )
    op.create_index(
        "ix_digests_user_generated",
        "digests",
        ["user_id", "generated_at", "id"],
    )

    op.create_table(
        "paper_authors",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("author_order", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "author_order >= 0",
            name="ck_paper_authors_order_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["author_id"],
            ["authors.id"],
            name="fk_paper_authors_author_id_authors",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name="fk_paper_authors_paper_id_papers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("paper_id", "author_id", name="pk_paper_authors"),
        sa.UniqueConstraint(
            "paper_id",
            "author_order",
            name="uq_paper_authors_paper_order",
        ),
    )
    op.create_index(
        "ix_paper_authors_author_paper",
        "paper_authors",
        ["author_id", "paper_id"],
    )

    op.create_table(
        "paper_versions",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_checksum", sa.String(length=64), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "version_number > 0",
            name="ck_paper_versions_version_number_positive",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name="fk_paper_versions_paper_id_papers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_versions"),
        sa.UniqueConstraint("id", "paper_id", name="uq_paper_versions_id_paper"),
        sa.UniqueConstraint(
            "paper_id",
            "version_number",
            name="uq_paper_versions_paper_version",
        ),
    )

    op.create_table(
        "pipeline_jobs",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column(
            "stage",
            string_enum(
                "fetch_metadata",
                "download_pdf",
                "parse_pdf",
                "summarize_paper",
                "chunk_paper",
                "embed_chunks",
                "assemble_digest",
                name="pipeline_stage",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            string_enum(
                "queued",
                "running",
                "succeeded",
                "failed",
                name="job_status",
            ),
            nullable=False,
        ),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("pipeline_version", sa.String(length=64), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_pipeline_jobs_attempts_non_negative",
        ),
        sa.CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_pipeline_jobs_time_range_valid",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name="fk_pipeline_jobs_paper_id_papers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_jobs"),
        sa.UniqueConstraint(
            "idempotency_key",
            name="uq_pipeline_jobs_idempotency_key",
        ),
    )
    op.create_index(
        "ix_pipeline_jobs_paper_status",
        "pipeline_jobs",
        ["paper_id", "status"],
    )
    op.create_index(
        "ix_pipeline_jobs_status_stage",
        "pipeline_jobs",
        ["status", "stage", "created_at"],
    )

    op.create_table(
        "qa_conversations",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name="fk_qa_conversations_paper_id_papers",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_qa_conversations_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_qa_conversations"),
    )
    op.create_index(
        "ix_qa_conversations_user_updated",
        "qa_conversations",
        ["user_id", "updated_at"],
    )

    op.create_table(
        "user_events",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "event_type",
            string_enum(
                "paper_impression",
                "paper_opened",
                "paper_saved",
                "paper_skipped",
                "paper_shared",
                "question_asked",
                "digest_dismissed",
                name="user_event_type",
            ),
            nullable=False,
        ),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("context", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_user_events_duration_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name="fk_user_events_paper_id_papers",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_events_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_events"),
    )
    op.create_index(
        "ix_user_events_user_occurred",
        "user_events",
        ["user_id", "occurred_at"],
    )

    op.create_table(
        "user_preferences",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("explicit_topics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("followed_authors", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("behavior_embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("behavior_embedding_model", sa.String(length=200), nullable=True),
        sa.Column("model_version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(behavior_embedding IS NULL AND behavior_embedding_model IS NULL) OR "
            "(behavior_embedding IS NOT NULL AND behavior_embedding_model IS NOT NULL)",
            name="ck_user_preferences_behavior_embedding_has_model",
        ),
        sa.CheckConstraint(
            "model_version > 0",
            name="ck_user_preferences_model_version_positive",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_user_preferences_user_id_users",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name="pk_user_preferences"),
    )

    op.create_table(
        "digest_entries",
        sa.Column("digest_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("recommendation_reason", sa.Text(), nullable=False),
        sa.CheckConstraint("rank >= 1", name="ck_digest_entries_rank_positive"),
        sa.CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1",
            name="ck_digest_entries_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["digest_id"],
            ["digests.id"],
            name="fk_digest_entries_digest_id_digests",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["paper_id"],
            ["papers.id"],
            name="fk_digest_entries_paper_id_papers",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("digest_id", "paper_id", name="pk_digest_entries"),
        sa.UniqueConstraint(
            "digest_id",
            "rank",
            name="uq_digest_entries_digest_rank",
        ),
    )

    op.create_table(
        "paper_chunks",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("section_title", sa.String(length=300), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer(), nullable=True),
        sa.Column("page_end", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(EMBEDDING_DIMENSIONS), nullable=True),
        sa.Column("embedding_model", sa.String(length=200), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL)",
            name="ck_paper_chunks_embedding_has_model",
        ),
        sa.CheckConstraint(
            "chunk_index >= 0",
            name="ck_paper_chunks_index_non_negative",
        ),
        sa.CheckConstraint(
            "page_end IS NULL OR page_start IS NULL OR page_end >= page_start",
            name="ck_paper_chunks_page_range_valid",
        ),
        sa.CheckConstraint(
            "page_start IS NULL OR page_start >= 1",
            name="ck_paper_chunks_page_start_positive",
        ),
        sa.CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_paper_chunks_token_count_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["paper_version_id", "paper_id"],
            ["paper_versions.id", "paper_versions.paper_id"],
            name="fk_paper_chunks_version_paper",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_chunks"),
        sa.UniqueConstraint(
            "paper_version_id",
            "chunk_index",
            name="uq_paper_chunks_version_index",
        ),
    )
    op.create_index(
        "ix_paper_chunks_content_hash",
        "paper_chunks",
        ["content_hash"],
    )
    op.create_index(
        "ix_paper_chunks_paper_index",
        "paper_chunks",
        ["paper_id", "chunk_index"],
    )

    op.create_table(
        "paper_summaries",
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("paper_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "status",
            string_enum("ready", "partial", name="summary_status"),
            nullable=False,
        ),
        sa.Column(
            "source_match_status",
            string_enum(
                "matched",
                "partial",
                "not_checked",
                name="source_match_status",
            ),
            nullable=False,
        ),
        sa.Column("content", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_snapshot", sa.String(length=200), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=False),
        sa.Column(
            "generation_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "estimated_cost >= 0",
            name="ck_paper_summaries_cost_non_negative",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_paper_summaries_input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_paper_summaries_latency_non_negative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_paper_summaries_output_tokens_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["paper_version_id", "paper_id"],
            ["paper_versions.id", "paper_versions.paper_id"],
            name="fk_paper_summaries_version_paper",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_paper_summaries"),
        sa.UniqueConstraint(
            "paper_version_id",
            "input_hash",
            "provider",
            "model_snapshot",
            "prompt_version",
            name="uq_paper_summaries_generation",
        ),
    )
    op.create_index(
        "ix_paper_summaries_paper_created",
        "paper_summaries",
        ["paper_id", "created_at"],
    )

    op.create_table(
        "qa_messages",
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "role",
            string_enum("user", "assistant", name="qa_role"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "source_match_status",
            string_enum(
                "matched",
                "partial",
                "insufficient_evidence",
                name="qa_source_match_status",
            ),
            nullable=True,
        ),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("model_snapshot", sa.String(length=200), nullable=True),
        sa.Column("prompt_version", sa.String(length=100), nullable=True),
        sa.Column("input_hash", sa.String(length=64), nullable=True),
        sa.Column("estimated_cost", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_qa_messages_cost_non_negative",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_qa_messages_input_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_qa_messages_latency_non_negative",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_qa_messages_output_tokens_non_negative",
        ),
        sa.CheckConstraint(
            "sequence_number >= 0",
            name="ck_qa_messages_sequence_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["qa_conversations.id"],
            name="fk_qa_messages_conversation_id_qa_conversations",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_qa_messages"),
        sa.UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_qa_messages_conversation_sequence",
        ),
    )


def downgrade() -> None:
    """Drop v0.1 tables in reverse dependency order.

    The vector extension is intentionally retained because PostgreSQL extensions are
    database-shared infrastructure and may be used by schemas outside Mneme.
    """
    op.drop_table("qa_messages")
    op.drop_table("paper_summaries")
    op.drop_table("paper_chunks")
    op.drop_table("digest_entries")
    op.drop_table("user_preferences")
    op.drop_table("user_events")
    op.drop_table("qa_conversations")
    op.drop_table("pipeline_jobs")
    op.drop_table("paper_versions")
    op.drop_table("paper_authors")
    op.drop_table("digests")
    op.drop_table("citations")
    op.drop_table("users")
    op.drop_table("papers")
    op.drop_table("authors")
