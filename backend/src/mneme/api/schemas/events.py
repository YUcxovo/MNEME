"""Frozen v0.1 behavioral-event request and response schemas."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, Field, StrictInt, field_validator, model_validator

from mneme.models.user import UserEventType
from mneme.repositories.events import EventRecord


class UserEvent(BaseModel):
    """One client-generated, idempotent behavioral event."""

    event_id: UUID
    event_type: UserEventType
    paper_id: UUID | None = None
    occurred_at: AwareDatetime
    duration_ms: StrictInt | None = Field(default=None, ge=0, le=2_147_483_647)
    context: dict[str, object] = Field(default_factory=dict)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def require_datetime_input(cls, value: object) -> object:
        """Accept ISO strings or datetime objects without numeric coercion."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError as error:
                raise ValueError("occurred_at must be an ISO 8601 date-time") from error
            return value
        raise ValueError("occurred_at must be an ISO 8601 date-time")

    @model_validator(mode="after")
    def validate_event_scope(self) -> Self:
        """Enforce the paper and duration semantics frozen for behavior-v1."""
        if self.event_type == UserEventType.DIGEST_DISMISSED:
            if self.paper_id is not None:
                raise ValueError("digest_dismissed must not include paper_id")
        elif self.paper_id is None:
            raise ValueError("paper-scoped events require paper_id")

        if self.event_type != UserEventType.PAPER_OPENED and self.duration_ms is not None:
            raise ValueError("duration_ms is only valid for paper_opened")
        return self

    def to_record(self) -> EventRecord:
        """Copy validated API data into the transport-neutral service record."""
        return EventRecord(
            event_id=self.event_id,
            event_type=self.event_type,
            paper_id=self.paper_id,
            occurred_at=self.occurred_at,
            duration_ms=self.duration_ms,
            context=dict(self.context),
        )


class EventIngestionResult(BaseModel):
    """Counts from one idempotent event batch."""

    accepted: int = Field(ge=0)
    duplicates: int = Field(ge=0)
