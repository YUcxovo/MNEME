"""Immutable research briefing snapshots and ranked paper entries."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mneme.models.base import Base, UUIDPrimaryKeyMixin, utc_now
from mneme.models.paper import Paper


class DigestType(StrEnum):
    """Supported briefing generation modes."""

    WEEKLY = "weekly"
    MANUAL = "manual"


class Digest(UUIDPrimaryKeyMixin, Base):
    """An immutable, reproducible briefing generated for one user."""

    __tablename__ = "digests"
    __table_args__ = (
        CheckConstraint(
            "preference_model_version > 0", name="ck_digests_preference_version_positive"
        ),
        Index("ix_digests_user_generated", "user_id", "generated_at", "id"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    digest_type: Mapped[DigestType] = mapped_column(
        Enum(
            DigestType,
            name="digest_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    preference_model_version: Mapped[int] = mapped_column(Integer, nullable=False)
    generator_version: Mapped[str] = mapped_column(String(100), nullable=False)

    entries: Mapped[list[DigestEntry]] = relationship(
        back_populates="digest",
        cascade="all, delete-orphan",
        order_by="DigestEntry.rank",
        passive_deletes=True,
    )


class DigestEntry(Base):
    """A ranked paper and its persisted recommendation explanation."""

    __tablename__ = "digest_entries"
    __table_args__ = (
        UniqueConstraint("digest_id", "rank", name="uq_digest_entries_digest_rank"),
        CheckConstraint("rank >= 1", name="ck_digest_entries_rank_positive"),
        CheckConstraint(
            "relevance_score >= 0 AND relevance_score <= 1",
            name="ck_digest_entries_score_range",
        ),
    )

    digest_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("digests.id", ondelete="CASCADE"), primary_key=True
    )
    paper_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="RESTRICT"), primary_key=True
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    relevance_score: Mapped[float] = mapped_column(Float, nullable=False)
    recommendation_reason: Mapped[str] = mapped_column(Text, nullable=False)

    digest: Mapped[Digest] = relationship(back_populates="entries")
    paper: Mapped[Paper] = relationship()
