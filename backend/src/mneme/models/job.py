"""Persisted state for separately retryable pipeline stages."""

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class PipelineStage(StrEnum):
    """Idempotent pipeline stages frozen by the reliability contract."""

    FETCH_METADATA = "fetch_metadata"
    DOWNLOAD_PDF = "download_pdf"
    PARSE_PDF = "parse_pdf"
    SUMMARIZE_PAPER = "summarize_paper"
    CHUNK_PAPER = "chunk_paper"
    EMBED_CHUNKS = "embed_chunks"
    ASSEMBLE_DIGEST = "assemble_digest"


class JobStatus(StrEnum):
    """Externally visible pipeline job states."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class PipelineJob(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Durable execution state for one idempotent pipeline stage."""

    __tablename__ = "pipeline_jobs"
    __table_args__ = (
        CheckConstraint("attempt_count >= 0", name="ck_pipeline_jobs_attempts_non_negative"),
        CheckConstraint(
            "paper_version_id IS NULL OR paper_id IS NOT NULL",
            name="ck_pipeline_jobs_version_requires_paper",
        ),
        CheckConstraint(
            "finished_at IS NULL OR started_at IS NULL OR finished_at >= started_at",
            name="ck_pipeline_jobs_time_range_valid",
        ),
        Index("ix_pipeline_jobs_status_stage", "status", "stage", "created_at"),
        Index("ix_pipeline_jobs_paper_status", "paper_id", "status"),
        Index("ix_pipeline_jobs_version_status", "paper_version_id", "status"),
        ForeignKeyConstraint(
            ["paper_version_id", "paper_id"],
            ["paper_versions.id", "paper_versions.paper_id"],
            name="fk_pipeline_jobs_version_paper",
            ondelete="CASCADE",
        ),
    )

    paper_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=True
    )
    paper_version_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    stage: Mapped[PipelineStage] = mapped_column(
        Enum(
            PipelineStage,
            name="pipeline_stage",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            name="job_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=JobStatus.QUEUED,
        nullable=False,
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
