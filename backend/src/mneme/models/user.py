"""User, explicit preference, and behavioral event models."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from mneme.models.base import Base, UUIDPrimaryKeyMixin, utc_now

EMBEDDING_DIMENSIONS = 1536


class UserEventType(StrEnum):
    """Behavioral signals accepted by the v0.1 event contract."""

    PAPER_IMPRESSION = "paper_impression"
    PAPER_OPENED = "paper_opened"
    PAPER_SAVED = "paper_saved"
    PAPER_SKIPPED = "paper_skipped"
    PAPER_SHARED = "paper_shared"
    QUESTION_ASKED = "question_asked"
    DIGEST_DISMISSED = "digest_dismissed"


class User(UUIDPrimaryKeyMixin, Base):
    """A pre-provisioned Mneme user."""

    __tablename__ = "users"

    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    preferences: Mapped[UserPreference] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    events: Mapped[list[UserEvent]] = relationship(back_populates="user")


class UserPreference(Base):
    """Explicit preferences and the derived behavior vector for one user."""

    __tablename__ = "user_preferences"
    __table_args__ = (
        CheckConstraint("model_version > 0", name="ck_user_preferences_model_version_positive"),
        CheckConstraint(
            "(behavior_embedding IS NULL AND behavior_embedding_model IS NULL) OR "
            "(behavior_embedding IS NOT NULL AND behavior_embedding_model IS NOT NULL)",
            name="ck_user_preferences_behavior_embedding_has_model",
        ),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    explicit_topics: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    followed_authors: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    behavior_embedding: Mapped[list[float] | None] = mapped_column(
        Vector(EMBEDDING_DIMENSIONS), nullable=True
    )
    behavior_embedding_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[User] = relationship(back_populates="preferences")


class UserEvent(UUIDPrimaryKeyMixin, Base):
    """An idempotent client-generated behavioral event."""

    __tablename__ = "user_events"
    __table_args__ = (
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_user_events_duration_non_negative",
        ),
        Index("ix_user_events_user_occurred", "user_id", "occurred_at"),
    )

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    paper_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[UserEventType] = mapped_column(
        Enum(
            UserEventType,
            name="user_event_type",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )
    context: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict, nullable=False)

    user: Mapped[User] = relationship(back_populates="events")
