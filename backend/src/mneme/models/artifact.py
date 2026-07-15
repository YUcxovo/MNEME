"""Revision-aware chunks and generated paper summaries."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mneme.models.base import Base, UUIDPrimaryKeyMixin, utc_now
from mneme.models.paper import PaperVersion
from mneme.models.user import EMBEDDING_DIMENSIONS


class SummaryStatus(StrEnum):
    """Usable summary states exposed by the API."""

    READY = "ready"
    PARTIAL = "partial"


class SourceMatchStatus(StrEnum):
    """Whether generated claims were matched to stored source chunks."""

    MATCHED = "matched"
    PARTIAL = "partial"
    NOT_CHECKED = "not_checked"


class PaperChunk(UUIDPrimaryKeyMixin, Base):
    """A deterministic chunk produced from one observed paper revision."""

    __tablename__ = "paper_chunks"
    __table_args__ = (
        ForeignKeyConstraint(
            ["paper_version_id", "paper_id"],
            ["paper_versions.id", "paper_versions.paper_id"],
            ondelete="CASCADE",
            name="fk_paper_chunks_version_paper",
        ),
        UniqueConstraint("paper_version_id", "chunk_index", name="uq_paper_chunks_version_index"),
        CheckConstraint("chunk_index >= 0", name="ck_paper_chunks_index_non_negative"),
        CheckConstraint(
            "page_start IS NULL OR page_start >= 1", name="ck_paper_chunks_page_start_positive"
        ),
        CheckConstraint(
            "page_end IS NULL OR page_start IS NULL OR page_end >= page_start",
            name="ck_paper_chunks_page_range_valid",
        ),
        CheckConstraint(
            "token_count IS NULL OR token_count >= 0",
            name="ck_paper_chunks_token_count_non_negative",
        ),
        CheckConstraint(
            "(embedding IS NULL AND embedding_model IS NULL) OR "
            "(embedding IS NOT NULL AND embedding_model IS NOT NULL)",
            name="ck_paper_chunks_embedding_has_model",
        ),
        Index("ix_paper_chunks_paper_index", "paper_id", "chunk_index"),
        Index("ix_paper_chunks_content_hash", "content_hash"),
    )

    paper_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    paper_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    section_title: Mapped[str | None] = mapped_column(String(300), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    paper_version: Mapped[PaperVersion] = relationship(back_populates="chunks")


class PaperSummary(UUIDPrimaryKeyMixin, Base):
    """A reproducible generated summary for one observed paper revision."""

    __tablename__ = "paper_summaries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["paper_version_id", "paper_id"],
            ["paper_versions.id", "paper_versions.paper_id"],
            ondelete="CASCADE",
            name="fk_paper_summaries_version_paper",
        ),
        UniqueConstraint(
            "paper_version_id",
            "input_hash",
            "provider",
            "model_snapshot",
            "prompt_version",
            name="uq_paper_summaries_generation",
        ),
        CheckConstraint("estimated_cost >= 0", name="ck_paper_summaries_cost_non_negative"),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_paper_summaries_input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_paper_summaries_output_tokens_non_negative",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_paper_summaries_latency_non_negative",
        ),
        Index("ix_paper_summaries_paper_created", "paper_id", "created_at"),
    )

    paper_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    paper_version_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    status: Mapped[SummaryStatus] = mapped_column(
        Enum(
            SummaryStatus,
            name="summary_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    source_match_status: Mapped[SourceMatchStatus] = mapped_column(
        Enum(
            SourceMatchStatus,
            name="source_match_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=SourceMatchStatus.NOT_CHECKED,
        nullable=False,
    )
    content: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(12, 6), default=Decimal("0"), nullable=False
    )
    generation_parameters: Mapped[dict[str, object]] = mapped_column(
        JSONB, default=dict, nullable=False
    )
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    paper_version: Mapped[PaperVersion] = relationship(back_populates="summaries")
