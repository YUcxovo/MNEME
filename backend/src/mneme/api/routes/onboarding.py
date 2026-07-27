"""Blocking seed-paper initialization for the local skeletal demo."""

from __future__ import annotations

from typing import Annotated, Final

import structlog
from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from mneme.api.dependencies.ai import TaskQueue, get_task_queue
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.routes.onboarding_support import (
    enqueue_seed_downloads,
    normalize_arxiv_reference,
    wait_for_seed_papers,
)
from mneme.api.schemas.digests import Digest
from mneme.api.schemas.onboarding import SeedInitializationRequest, SeedInitializationResult
from mneme.api.schemas.preferences import Preferences
from mneme.core.config import Settings, get_settings
from mneme.db.dependencies import get_session
from mneme.models.digest import DigestEntry, DigestType
from mneme.models.paper import Paper, PaperAuthor
from mneme.repositories.citation_graph import CitationIdentityConflict
from mneme.repositories.digests import DigestRepository
from mneme.repositories.preferences import PreferenceRepository
from mneme.services.arxiv.client import ArxivClient, ArxivClientError
from mneme.services.arxiv.ingestion import ArxivIngestionService
from mneme.services.arxiv.parser import ArxivParseError
from mneme.services.recommendation import DigestBundle
from mneme.services.seed_graph import (
    InsufficientSeedGraphCandidates,
    SeedGraphCandidateService,
)
from mneme.services.semantic_scholar import (
    SemanticScholarClient,
    SemanticScholarClientError,
)

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/onboarding", tags=["demo"])

_CANDIDATE_FETCH_LIMIT: Final = 8
_GRAPH_NEIGHBOR_LIMIT: Final = 20
_LIBRARY_SIZE: Final = 5


def get_request_settings() -> Settings:
    """Return process settings; overridable in tests."""
    return get_settings()


@router.post(
    "/seed",
    operation_id="initializeFromSeed",
    response_model=SeedInitializationResult,
    responses={"default": {"model": ErrorResponse}},
)
async def initialize_from_seed(
    payload: SeedInitializationRequest,
    principal: Annotated[Principal, Depends(require_principal)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    settings: Annotated[Settings, Depends(get_request_settings)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> SeedInitializationResult:
    """Prepare five citation-related papers before returning the first briefing."""
    try:
        seed_arxiv_id = normalize_arxiv_reference(payload.arxiv_reference)
    except ValueError as error:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_arxiv_reference", str(error)) from None

    try:
        async with ArxivClient(settings) as client:
            seed_feed = await client.fetch_by_id(seed_arxiv_id)
            if len(seed_feed.records) != 1:
                raise ApiError(
                    status.HTTP_404_NOT_FOUND,
                    "seed_paper_not_found",
                    "The seed paper could not be found on arXiv.",
                )
            seed_record = seed_feed.records[0]
            ingestion = ArxivIngestionService(client, session)
            seed_result = await ingestion.persist_feed_detailed(seed_feed)

            candidate_source = "citation_graph"
            try:
                async with SemanticScholarClient(settings) as semantic_client:
                    graph_candidates = SeedGraphCandidateService(client, semantic_client)
                    selection = await graph_candidates.discover(
                        seed_arxiv_id,
                        library_size=_LIBRARY_SIZE,
                        neighbor_limit=_GRAPH_NEIGHBOR_LIMIT,
                    )
                    candidate_result = await ingestion.persist_feed_detailed(selection.feed)
                    graph_result = await graph_candidates.persist(
                        session,
                        center_paper_id=seed_result.revisions[0].paper_id,
                        candidates=selection,
                    )
                logger.info(
                    "seed_graph_candidates_prepared",
                    seed_arxiv_id=seed_arxiv_id,
                    paper_count=len(candidate_result.revisions),
                    reference_edges=graph_result.references.observed,
                    citation_edges=graph_result.citations.observed,
                )
            except (
                ArxivClientError,
                ArxivParseError,
                CitationIdentityConflict,
                InsufficientSeedGraphCandidates,
                SemanticScholarClientError,
            ) as error:
                candidate_source = "same_category_fallback"
                logger.warning(
                    "seed_graph_candidates_unavailable",
                    seed_arxiv_id=seed_arxiv_id,
                    error_type=type(error).__name__,
                )
                candidate_feed = await client.fetch_by_category(
                    seed_record.primary_category,
                    max_results=_CANDIDATE_FETCH_LIMIT,
                )
                candidate_result = await ingestion.persist_feed_detailed(candidate_feed)
    except ApiError:
        raise
    except ValueError as error:
        raise ApiError(status.HTTP_400_BAD_REQUEST, "invalid_arxiv_reference", str(error)) from None
    except (ArxivClientError, ArxivParseError) as error:
        logger.warning("seed_arxiv_fetch_failed", error_type=type(error).__name__)
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "arxiv_unavailable",
            "The backend could not read the requested paper from arXiv.",
        ) from error

    candidates = tuple(
        revision for revision in candidate_result.revisions if revision.arxiv_id != seed_arxiv_id
    )[:_LIBRARY_SIZE]
    if len(candidates) != _LIBRARY_SIZE:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "insufficient_related_papers",
            "arXiv did not return five related papers for this seed.",
        )

    preference = await PreferenceRepository(session).replace_preferences(
        principal.user_id,
        topics=[seed_record.primary_category],
        followed_authors=[],
    )
    if preference is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "user_not_found",
            "The configured demo user has not been bootstrapped.",
        )

    revisions_to_prepare = (
        (seed_result.revisions[0], *candidates)
        if candidate_source == "citation_graph"
        else candidates
    )
    paper_ids = await enqueue_seed_downloads(session, queue, revisions_to_prepare)
    await wait_for_seed_papers(session, paper_ids)

    candidate_order = [revision.paper_id for revision in candidates]
    prepared_papers = list(
        (
            await session.scalars(
                select(Paper)
                .where(Paper.id.in_(candidate_order))
                .options(selectinload(Paper.author_links).selectinload(PaperAuthor.author))
            )
        ).all()
    )
    papers_by_id = {paper.id: paper for paper in prepared_papers}
    entries = [
        DigestEntry(
            paper_id=paper_id,
            rank=rank,
            relevance_score=round(1.0 - ((rank - 1) * 0.05), 2),
            recommendation_reason=(
                "Connected to your seed paper through its citation neighborhood."
                if candidate_source == "citation_graph"
                else f"Same arXiv category as your seed paper: {seed_record.primary_category}"
            ),
        )
        for rank, paper_id in enumerate(candidate_order, start=1)
    ]
    digest_model = await DigestRepository(session).create_digest(
        user_id=principal.user_id,
        digest_type=DigestType.MANUAL,
        preference_model_version=preference.model_version,
        generator_version="seed-onboarding-v1",
        entries=entries,
    )
    await session.commit()
    digest = Digest.from_bundle(
        DigestBundle(
            digest=digest_model,
            entries=entries,
            papers_by_id=papers_by_id,
        )
    )
    if len(digest.entries) != _LIBRARY_SIZE:
        raise ApiError(
            status.HTTP_502_BAD_GATEWAY,
            "briefing_incomplete",
            "The backend could not assemble a five-paper briefing.",
        )

    logger.info(
        "seed_initialization_completed",
        seed_arxiv_id=seed_arxiv_id,
        category=seed_record.primary_category,
        paper_count=len(digest.entries),
        candidate_source=candidate_source,
    )
    return SeedInitializationResult(
        seed_arxiv_id=seed_arxiv_id,
        category=seed_record.primary_category,
        paper_count=len(digest.entries),
        preferences=Preferences(
            topics=preference.topics,
            followed_authors=preference.followed_authors,
            model_version=preference.model_version,
            updated_at=preference.updated_at,
        ),
        digest=digest,
    )
