"""Explicit preference endpoints for the authenticated demo user."""

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import TaskQueue, get_task_queue
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_preference_repository
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.routes.onboarding_support import (
    enqueue_seed_downloads,
    wait_for_refresh_papers,
)
from mneme.api.schemas.digests import Digest
from mneme.api.schemas.preferences import (
    PreferenceRefreshResult,
    Preferences,
    PreferenceUpdate,
)
from mneme.core.config import Settings, get_settings
from mneme.db.dependencies import get_session
from mneme.models.base import utc_now
from mneme.models.digest import DigestType
from mneme.repositories.digests import DigestRepository
from mneme.repositories.preferences import PreferenceRepository, PreferenceSnapshot
from mneme.services.arxiv.client import (
    TOPIC_SEARCH_MAX_TERMS,
    ArxivClient,
    ArxivClientError,
)
from mneme.services.arxiv.ingestion import ArxivIngestionService
from mneme.services.arxiv.parser import ArxivParseError
from mneme.services.recommendation import RecommendedDigestService

router = APIRouter(prefix="/users/me/preferences", tags=["preferences"])

_REFRESH_FETCH_LIMIT: Final = 5


def get_request_settings() -> Settings:
    """Return process settings; overridable in tests."""
    return get_settings()


def _to_response(snapshot: PreferenceSnapshot) -> Preferences:
    return Preferences(
        topics=snapshot.topics,
        followed_authors=snapshot.followed_authors,
        model_version=snapshot.model_version,
        updated_at=snapshot.updated_at,
    )


def _user_not_found() -> ApiError:
    return ApiError(
        status.HTTP_404_NOT_FOUND,
        "user_not_found",
        "Mneme has not been initialized for this user.",
    )


@router.get(
    "",
    response_model=Preferences,
    operation_id="getPreferences",
    responses={"default": {"model": ErrorResponse}},
)
async def get_preferences(
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PreferenceRepository, Depends(get_preference_repository)],
) -> Preferences:
    """Return both explicit preference lists and their model version."""
    snapshot = await repository.get_preferences(principal.user_id)
    if snapshot is None:
        raise _user_not_found()
    return _to_response(snapshot)


@router.put(
    "",
    response_model=Preferences,
    operation_id="updatePreferences",
    responses={"default": {"model": ErrorResponse}},
)
async def update_preferences(
    update: PreferenceUpdate,
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PreferenceRepository, Depends(get_preference_repository)],
) -> Preferences:
    """Completely replace the authenticated user's explicit preferences."""
    snapshot = await repository.replace_preferences(
        principal.user_id,
        topics=update.topics,
        followed_authors=update.followed_authors,
    )
    if snapshot is None:
        raise _user_not_found()
    return _to_response(snapshot)


@router.post(
    "/refresh",
    response_model=PreferenceRefreshResult,
    operation_id="refreshPreferences",
    responses={"default": {"model": ErrorResponse}},
)
async def refresh_preferences(
    update: PreferenceUpdate,
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PreferenceRepository, Depends(get_preference_repository)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PreferenceRefreshResult:
    """Save interests, prepare a bounded real feed, and return a new digest."""
    # Persist user intent first. Downstream metadata and document jobs are
    # durable/idempotent, so a failed refresh can be retried without losing the
    # preference edit or duplicating work.
    snapshot = await repository.replace_preferences(
        principal.user_id,
        topics=update.topics,
        followed_authors=update.followed_authors,
    )
    if snapshot is None:
        raise _user_not_found()

    prepared_paper_ids: tuple[UUID, ...] = ()
    topics = tuple(snapshot.topics[:TOPIC_SEARCH_MAX_TERMS])
    if topics:
        max_results = min(
            _REFRESH_FETCH_LIMIT,
            settings.arxiv_daily_max_results,
            settings.arxiv_max_results,
        )
        try:
            async with ArxivClient(settings) as client:
                feed = await client.fetch_by_topics(topics, max_results=max_results)
                observed = await ArxivIngestionService(client, session).persist_feed_detailed(feed)
        except (ArxivClientError, ArxivParseError) as error:
            raise ApiError(
                status.HTTP_502_BAD_GATEWAY,
                "arxiv_unavailable",
                "Mneme could not load papers for the selected interests. Try again.",
            ) from error

        revisions = tuple(
            {
                (revision.paper_id, revision.paper_version_id): revision
                for revision in observed.revisions
            }.values()
        )
        await enqueue_seed_downloads(session, queue, revisions)
        prepared_paper_ids = await wait_for_refresh_papers(session, revisions)
        if not prepared_paper_ids:
            raise ApiError(
                status.HTTP_502_BAD_GATEWAY,
                "paper_preparation_failed",
                "Mneme could not prepare papers for the selected interests. Try again.",
            )

    service = RecommendedDigestService(
        DigestRepository(session),
        candidate_days=settings.ai_recommendation_candidate_days,
        max_entries=settings.ai_recommendation_max_entries,
    )
    bundle = await service.generate(
        principal.user_id,
        digest_type=DigestType.MANUAL,
        as_of=utc_now(),
        include_paper_ids=prepared_paper_ids,
    )
    if not bundle.entries:
        await session.rollback()
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "briefing_unavailable",
            "Mneme could not prepare a new briefing from the available papers.",
        )
    await session.commit()
    return PreferenceRefreshResult(
        preferences=_to_response(snapshot),
        digest=Digest.from_bundle(bundle),
    )
