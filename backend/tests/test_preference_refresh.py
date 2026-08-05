"""Focused orchestration tests for interest-driven briefing refreshes."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import TaskQueue
from mneme.api.dependencies.auth import Principal
from mneme.api.errors import ApiError
from mneme.api.routes import preferences
from mneme.api.schemas.preferences import PreferenceUpdate
from mneme.core.config import Settings
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.paper import Paper, ProcessingStatus
from mneme.repositories.preferences import PreferenceSnapshot
from mneme.services.arxiv.client import ArxivHTTPError
from mneme.services.arxiv.ingestion import ArxivObservedRevision
from mneme.services.recommendation import DigestBundle

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
NOW = datetime(2026, 8, 5, 12, tzinfo=UTC)


@pytest.mark.base
@pytest.mark.api
def test_refresh_endpoint_is_additive_and_authenticated() -> None:
    application = FastAPI()
    application.include_router(preferences.router, prefix="/v1")

    operation = application.openapi()["paths"]["/v1/users/me/preferences/refresh"]["post"]

    assert operation["operationId"] == "refreshPreferences"
    assert operation["security"] == [{"demoToken": []}]


def _bundle() -> DigestBundle:
    paper = Paper(
        id=uuid4(),
        arxiv_id="2608.00001",
        title="Interfaces for collaborative programming",
        abstract="An HCI study of developer tools.",
        primary_category="cs.HC",
        categories=["cs.HC"],
        pdf_url="https://arxiv.org/pdf/2608.00001",
        source_license=None,
        processing_status=ProcessingStatus.READY,
        published_at=NOW - timedelta(days=1),
        source_updated_at=NOW,
    )
    paper.author_links = []
    digest = Digest(
        id=uuid4(),
        user_id=USER_ID,
        digest_type=DigestType.MANUAL,
        generated_at=NOW,
        preference_model_version=1,
        generator_version="recommender-v2",
    )
    entry = DigestEntry(
        digest_id=digest.id,
        paper_id=paper.id,
        rank=1,
        relevance_score=0.9,
        recommendation_reason="Matches your topics: hci",
    )
    return DigestBundle(digest=digest, entries=[entry], papers_by_id={paper.id: paper})


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_refresh_prepares_real_topic_feed_and_returns_new_paper_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = PreferenceSnapshot(
        topics=["hci"],
        followed_authors=[],
        model_version=1,
        updated_at=NOW,
    )
    repository = MagicMock()
    repository.replace_preferences = AsyncMock(return_value=snapshot)
    revision = ArxivObservedRevision(
        paper_id=uuid4(),
        paper_version_id=uuid4(),
        arxiv_id="2608.00001",
        version_number=1,
        version_created=True,
    )
    feed = SimpleNamespace(records=(SimpleNamespace(arxiv_id=revision.arxiv_id),))
    client = MagicMock()
    client.fetch_by_topics = AsyncMock(return_value=feed)
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    ingestion = MagicMock()
    ingestion.persist_feed_detailed = AsyncMock(
        return_value=SimpleNamespace(revisions=(revision, revision))
    )
    enqueue = AsyncMock(return_value=(revision.paper_id,))
    wait = AsyncMock(return_value=(revision.paper_id,))
    bundle = _bundle()
    service = MagicMock()
    service.generate = AsyncMock(return_value=bundle)
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()

    monkeypatch.setattr(preferences, "ArxivClient", MagicMock(return_value=client_context))
    monkeypatch.setattr(
        preferences,
        "ArxivIngestionService",
        MagicMock(return_value=ingestion),
    )
    monkeypatch.setattr(preferences, "enqueue_seed_downloads", enqueue)
    monkeypatch.setattr(preferences, "wait_for_refresh_papers", wait)
    monkeypatch.setattr(preferences, "DigestRepository", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        preferences,
        "RecommendedDigestService",
        MagicMock(return_value=service),
    )

    result = asyncio.run(
        preferences.refresh_preferences(
            PreferenceUpdate(topics=["HCI"], followed_authors=[]),
            Principal(user_id=USER_ID),
            repository,
            cast(TaskQueue, MagicMock()),
            Settings(arxiv_daily_max_results=20, _env_file=None),
            cast(AsyncSession, session),
        )
    )

    assert result.preferences.topics == ["hci"]
    assert [entry.paper.id for entry in result.digest.entries] == list(bundle.papers_by_id)
    client.fetch_by_topics.assert_awaited_once_with(("hci",), max_results=5)
    ingestion.persist_feed_detailed.assert_awaited_once_with(feed)
    enqueue.assert_awaited_once()
    enqueue_call = enqueue.await_args
    assert enqueue_call is not None
    assert enqueue_call.args[2] == (revision,)
    wait.assert_awaited_once_with(session, (revision,))
    generate_call = service.generate.await_args
    assert generate_call is not None
    assert generate_call.kwargs["digest_type"] is DigestType.MANUAL
    assert generate_call.kwargs["include_paper_ids"] == (revision.paper_id,)
    session.commit.assert_awaited_once()


@pytest.mark.base
@pytest.mark.api
def test_refresh_arxiv_failure_is_safe_and_does_not_report_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = PreferenceSnapshot(
        topics=["hci"], followed_authors=[], model_version=1, updated_at=NOW
    )
    repository = MagicMock()
    repository.replace_preferences = AsyncMock(return_value=snapshot)
    client = MagicMock()
    client.fetch_by_topics = AsyncMock(side_effect=ArxivHTTPError(503))
    client_context = MagicMock()
    client_context.__aenter__ = AsyncMock(return_value=client)
    client_context.__aexit__ = AsyncMock(return_value=None)
    digest_service = MagicMock()

    monkeypatch.setattr(preferences, "ArxivClient", MagicMock(return_value=client_context))
    monkeypatch.setattr(preferences, "RecommendedDigestService", digest_service)

    with pytest.raises(ApiError) as captured:
        asyncio.run(
            preferences.refresh_preferences(
                PreferenceUpdate(topics=["hci"], followed_authors=[]),
                Principal(user_id=USER_ID),
                repository,
                cast(TaskQueue, MagicMock()),
                Settings(_env_file=None),
                cast(AsyncSession, MagicMock(spec=AsyncSession)),
            )
        )

    assert captured.value.status_code == 502
    assert captured.value.code == "arxiv_unavailable"
    assert "503" not in captured.value.message
    digest_service.assert_not_called()


@pytest.mark.base
@pytest.mark.api
def test_refresh_without_a_usable_digest_rolls_back_digest_and_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = PreferenceSnapshot(topics=[], followed_authors=[], model_version=1, updated_at=NOW)
    repository = MagicMock()
    repository.replace_preferences = AsyncMock(return_value=snapshot)
    digest = Digest(
        id=uuid4(),
        user_id=USER_ID,
        digest_type=DigestType.MANUAL,
        generated_at=NOW,
        preference_model_version=1,
        generator_version="recommender-v2",
    )
    service = MagicMock()
    service.generate = AsyncMock(
        return_value=DigestBundle(digest=digest, entries=[], papers_by_id={})
    )
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    monkeypatch.setattr(preferences, "DigestRepository", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(
        preferences,
        "RecommendedDigestService",
        MagicMock(return_value=service),
    )

    with pytest.raises(ApiError) as captured:
        asyncio.run(
            preferences.refresh_preferences(
                PreferenceUpdate(topics=[], followed_authors=[]),
                Principal(user_id=USER_ID),
                repository,
                cast(TaskQueue, MagicMock()),
                Settings(_env_file=None),
                cast(AsyncSession, session),
            )
        )

    assert captured.value.status_code == 502
    assert captured.value.code == "briefing_unavailable"
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()
