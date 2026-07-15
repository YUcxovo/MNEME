"""Paper catalog, observed arXiv revisions, and ordered authorship."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now

if TYPE_CHECKING:
    from mneme.models.artifact import PaperChunk, PaperSummary


class ProcessingStatus(StrEnum):
    """Current state of a paper in the processing pipeline."""

    METADATA_ONLY = "metadata_only"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    PARTIAL = "partial"
    FAILED = "failed"


class Paper(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """The latest observed metadata snapshot for one arXiv work."""

    __tablename__ = "papers"
    __table_args__ = (
        Index("ix_papers_published_id", "published_at", "id"),
        Index("ix_papers_category_published", "primary_category", "published_at", "id"),
    )

    arxiv_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str] = mapped_column(Text, nullable=False)
    primary_category: Mapped[str] = mapped_column(String(64), nullable=False)
    categories: Mapped[list[str]] = mapped_column(ARRAY(String(64)), nullable=False)
    pdf_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_license: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processing_status: Mapped[ProcessingStatus] = mapped_column(
        Enum(
            ProcessingStatus,
            name="processing_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        default=ProcessingStatus.METADATA_ONLY,
        nullable=False,
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    versions: Mapped[list[PaperVersion]] = relationship(
        back_populates="paper", cascade="all, delete-orphan", passive_deletes=True
    )
    author_links: Mapped[list[PaperAuthor]] = relationship(
        back_populates="paper",
        cascade="all, delete-orphan",
        order_by="PaperAuthor.author_order",
        passive_deletes=True,
    )


class PaperVersion(UUIDPrimaryKeyMixin, Base):
    """An arXiv revision observed by Mneme."""

    __tablename__ = "paper_versions"
    __table_args__ = (
        UniqueConstraint("id", "paper_id", name="uq_paper_versions_id_paper"),
        UniqueConstraint("paper_id", "version_number", name="uq_paper_versions_paper_version"),
        CheckConstraint("version_number > 0", name="ck_paper_versions_version_number_positive"),
    )

    paper_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), nullable=False
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    source_checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    paper: Mapped[Paper] = relationship(back_populates="versions")
    chunks: Mapped[list[PaperChunk]] = relationship(
        back_populates="paper_version", cascade="all, delete-orphan", passive_deletes=True
    )
    summaries: Mapped[list[PaperSummary]] = relationship(
        back_populates="paper_version", cascade="all, delete-orphan", passive_deletes=True
    )


class Author(UUIDPrimaryKeyMixin, Base):
    """A normalized M1 author identity with source display text."""

    __tablename__ = "authors"

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    semantic_scholar_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    paper_links: Mapped[list[PaperAuthor]] = relationship(
        back_populates="author", passive_deletes=True
    )


class PaperAuthor(Base):
    """Ordered many-to-many association between papers and authors."""

    __tablename__ = "paper_authors"
    __table_args__ = (
        UniqueConstraint("paper_id", "author_order", name="uq_paper_authors_paper_order"),
        CheckConstraint("author_order >= 0", name="ck_paper_authors_order_non_negative"),
        Index("ix_paper_authors_author_paper", "author_id", "paper_id"),
    )

    paper_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="CASCADE"), primary_key=True
    )
    author_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("authors.id", ondelete="CASCADE"), primary_key=True
    )
    author_order: Mapped[int] = mapped_column(Integer, nullable=False)

    paper: Mapped[Paper] = relationship(back_populates="author_links")
    author: Mapped[Author] = relationship(back_populates="paper_links")
