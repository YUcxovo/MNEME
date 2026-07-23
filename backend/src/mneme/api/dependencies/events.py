"""Dependencies for behavioral-event ingestion."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.core.config import Settings
from mneme.db.dependencies import get_session
from mneme.services.events import BehaviorEventService


def get_event_settings(request: Request) -> Settings:
    """Return the application-scoped settings used by event aggregation."""
    settings: Settings = request.app.state.settings
    return settings


async def get_behavior_event_service(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_event_settings)],
) -> BehaviorEventService:
    """Bind event ingestion to the request transaction and embedding model."""
    return BehaviorEventService(session, embedding_model=settings.ai_embedding_model)
