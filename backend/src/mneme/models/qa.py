"""Single-paper Q&A conversations and reproducible messages."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
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

from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, utc_now


class QaRole(StrEnum):
    """Supported persisted conversation roles."""

    USER = "user"
    ASSISTANT = "assistant"


class QaSourceMatchStatus(StrEnum):
    """Source matching result for an assistant answer."""

    MATCHED = "matched"
    PARTIAL = "partial"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class QaCitationResolution(StrEnum):
    """How an answer's citation contract was resolved.

    ``VERIFIED`` answers passed verification on the first generation;
    ``CORRECTED`` answers passed (or honestly refused) after the single
    bounded regeneration; ``UNRESOLVED`` answers failed verification twice
    and are returned as an explicit insufficient state instead of retaining
    unsupported citations. Refusals and weak-evidence short-circuits carry
    ``NOT_APPLICABLE``.
    """

    VERIFIED = "verified"
    CORRECTED = "corrected"
    UNRESOLVED = "unresolved"
    NOT_APPLICABLE = "not_applicable"


class QaConversation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A conversation explicitly scoped to one paper."""

    __tablename__ = "qa_conversations"
    __table_args__ = (Index("ix_qa_conversations_user_updated", "user_id", "updated_at"),)

    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    paper_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("papers.id", ondelete="RESTRICT"), nullable=False
    )

    messages: Mapped[list[QaMessage]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="QaMessage.sequence_number",
        passive_deletes=True,
    )


class QaMessage(UUIDPrimaryKeyMixin, Base):
    """A user question or generated answer with optional generation telemetry."""

    __tablename__ = "qa_messages"
    __table_args__ = (
        UniqueConstraint(
            "conversation_id", "sequence_number", name="uq_qa_messages_conversation_sequence"
        ),
        CheckConstraint("sequence_number >= 0", name="ck_qa_messages_sequence_non_negative"),
        CheckConstraint(
            "estimated_cost IS NULL OR estimated_cost >= 0",
            name="ck_qa_messages_cost_non_negative",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_qa_messages_input_tokens_non_negative",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_qa_messages_output_tokens_non_negative",
        ),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_qa_messages_latency_non_negative",
        ),
        CheckConstraint(
            "model_calls IS NULL OR model_calls >= 0",
            name="ck_qa_messages_model_calls_non_negative",
        ),
    )

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("qa_conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[QaRole] = mapped_column(
        Enum(
            QaRole,
            name="qa_role",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list[dict[str, object]]] = mapped_column(JSONB, default=list, nullable=False)
    source_match_status: Mapped[QaSourceMatchStatus | None] = mapped_column(
        Enum(
            QaSourceMatchStatus,
            name="qa_source_match_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=True,
    )
    citation_resolution: Mapped[QaCitationResolution | None] = mapped_column(
        Enum(
            QaCitationResolution,
            name="qa_citation_resolution",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda values: [item.value for item in values],
        ),
        nullable=True,
    )
    model_calls: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    model_snapshot: Mapped[str | None] = mapped_column(String(200), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(12, 6), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False
    )

    conversation: Mapped[QaConversation] = relationship(back_populates="messages")
