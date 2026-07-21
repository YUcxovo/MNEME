"""Authenticated recommended digest endpoint (Milestone 3)."""

from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import get_digest_repository
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.digests import Digest, DigestPage
from mneme.api.schemas.jobs import Job
from mneme.core.config import Settings, get_settings
from mneme.db.dependencies import get_session
from mneme.repositories.digests import (
    DigestRepository,
    InvalidDigestCursorError,
    decode_digest_cursor,
)
from mneme.services.recommendation import RecommendedDigestService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/digests", tags=["ai"])


def get_request_settings() -> Settings:
    """Return process settings; overridable in tests."""
    return get_settings()


@router.get(
    "",
    response_model=DigestPage,
    operation_id="listDigests",
    responses={"default": {"model": ErrorResponse}},
)
async def list_digests(
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[DigestRepository, Depends(get_digest_repository)],
    cursor: Annotated[
        str | None,
        Query(description="Opaque cursor for descending generated_at and digest ID pagination"),
    ] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> DigestPage:
    """Return the authenticated user's persisted research briefings."""
    try:
        decoded_cursor = decode_digest_cursor(cursor) if cursor is not None else None
    except InvalidDigestCursorError:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_cursor",
            "The pagination cursor is invalid.",
        ) from None

    page = await repository.list_digests(
        user_id=principal.user_id,
        limit=limit,
        cursor=decoded_cursor,
    )
    return DigestPage(
        items=[Digest.from_model(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "/recommended",
    response_model=Digest,
    operation_id="generateRecommendedDigest",
    responses={
        status.HTTP_202_ACCEPTED: {"model": Job},
        "default": {"model": ErrorResponse},
    },
)
async def generate_recommended_digest(
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[DigestRepository, Depends(get_digest_repository)],
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Digest:
    """Return a fresh recommended digest, generating one when needed.

    Scoring uses stored preferences and embeddings only (no LLM call), so
    generation is synchronous; the contract's 202 branch stays reserved for
    a future slow path.
    """
    service = RecommendedDigestService(
        repository,
        candidate_days=settings.ai_recommendation_candidate_days,
        max_entries=settings.ai_recommendation_max_entries,
    )
    bundle = await service.get_or_generate(principal.user_id)
    await session.commit()
    logger.info(
        "recommended_digest_served",
        user_id=str(principal.user_id),
        digest_id=str(bundle.digest.id),
        entries=len(bundle.entries),
    )
    return Digest.from_bundle(bundle)
