"""Authenticated behavioral-event ingestion endpoint."""

from typing import Annotated

from fastapi import APIRouter, Body, Depends, status

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.events import get_behavior_event_service
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.events import EventIngestionResult, UserEvent
from mneme.services.events import (
    BehaviorEventService,
    EventPaperNotFoundError,
    EventUserNotFoundError,
)

router = APIRouter(prefix="/events", tags=["behavior"])


@router.post(
    "",
    response_model=EventIngestionResult,
    operation_id="ingestEvents",
    responses={"default": {"model": ErrorResponse}},
)
async def ingest_events(
    events: Annotated[list[UserEvent], Body(max_length=500)],
    principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[BehaviorEventService, Depends(get_behavior_event_service)],
) -> EventIngestionResult:
    """Idempotently store a raw event batch and refresh behavior-v1."""
    try:
        result = await service.ingest(
            principal.user_id,
            [event.to_record() for event in events],
        )
    except EventUserNotFoundError:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "The authenticated user does not exist.",
        ) from None
    except EventPaperNotFoundError:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "One or more referenced papers do not exist.",
        ) from None
    return EventIngestionResult(
        accepted=result.accepted,
        duplicates=result.duplicates,
    )
