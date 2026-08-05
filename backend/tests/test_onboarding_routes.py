"""Focused tests for local-demo seed reference handling."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import TaskQueue
from mneme.api.dependencies.auth import Principal
from mneme.api.errors import ApiError
from mneme.api.routes import onboarding
from mneme.api.routes.onboarding_support import normalize_arxiv_reference
from mneme.api.schemas.onboarding import SeedInitializationRequest
from mneme.core.config import Settings
from mneme.models.digest import DigestType
from mneme.models.paper import ProcessingStatus
from mneme.services.arxiv.client import ArxivHTTPError
from mneme.services.seed_graph import (
    InsufficientSeedGraphCandidates,
    SeedGraphMetadataUnavailable,
)


@pytest.mark.parametrize(
    ("reference", "expected"),
    [
        ("2607.01234", "2607.01234"),
        ("2607.01234v2", "2607.01234"),
        ("https://arxiv.org/abs/2607.01234v3", "2607.01234"),
        ("https://arxiv.org/pdf/2607.01234v3.pdf", "2607.01234"),
        ("https://export.arxiv.org/abs/hep-th/9901001", "hep-th/9901001"),
    ],
)
def test_normalize_arxiv_reference(reference: str, expected: str) -> None:
    assert normalize_arxiv_reference(reference) == expected


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "not-an-id",
        "https://example.com/abs/2607.01234",
        "https://arxiv.org/search/?query=agents",
    ],
)
def test_invalid_arxiv_reference_is_rejected(reference: str) -> None:
    with pytest.raises(ValueError):
        normalize_arxiv_reference(reference)


@pytest.mark.base
@pytest.mark.api
@pytest.mark.parametrize(
    "discovery_error",
    [
        SeedGraphMetadataUnavailable(
            "arXiv citation-neighbor metadata remained unavailable after retry"
        ),
        InsufficientSeedGraphCandidates(
            "Semantic Scholar has no matching record for the seed paper"
        ),
        InsufficientSeedGraphCandidates("The seed has too few arXiv-resolvable citation neighbors"),
    ],
    ids=["neighbor-metadata-unavailable", "seed-not-in-s2", "too-few-citation-neighbors"],
)
def test_graph_discovery_failure_uses_real_same_category_fallback(
    monkeypatch: pytest.MonkeyPatch,
    discovery_error: Exception,
) -> None:
    observed_at = datetime(2026, 8, 4, tzinfo=UTC)
    seed_revision = SimpleNamespace(paper_id=uuid4(), arxiv_id="1706.03762")
    fallback_revisions = tuple(
        SimpleNamespace(paper_id=uuid4(), arxiv_id=f"2607.0000{index}") for index in range(1, 6)
    )
    seed_feed = SimpleNamespace(
        records=(SimpleNamespace(primary_category="cs.AI"),),
    )
    category_feed = SimpleNamespace(records=tuple(SimpleNamespace() for _ in range(5)))
    arxiv_client = MagicMock()
    arxiv_client.fetch_by_id = AsyncMock(return_value=seed_feed)
    arxiv_client.fetch_by_category = AsyncMock(return_value=category_feed)
    arxiv_context = MagicMock()
    arxiv_context.__aenter__ = AsyncMock(return_value=arxiv_client)
    arxiv_context.__aexit__ = AsyncMock(return_value=None)

    semantic_context = MagicMock()
    semantic_context.__aenter__ = AsyncMock(return_value=MagicMock())
    semantic_context.__aexit__ = AsyncMock(return_value=None)

    ingestion = MagicMock()
    ingestion.persist_feed_detailed = AsyncMock(
        side_effect=(
            SimpleNamespace(revisions=(seed_revision,)),
            SimpleNamespace(revisions=fallback_revisions),
        )
    )

    if isinstance(discovery_error, SeedGraphMetadataUnavailable):
        discovery_error.__cause__ = ArxivHTTPError(429)
    graph_candidates = MagicMock()
    graph_candidates.discover = AsyncMock(side_effect=discovery_error)
    graph_candidates.persist = AsyncMock()

    preferences = MagicMock()
    preferences.replace_preferences = AsyncMock(
        return_value=SimpleNamespace(
            topics=["cs.AI"],
            followed_authors=[],
            model_version=1,
            updated_at=observed_at,
        )
    )
    prepared_papers = [
        SimpleNamespace(
            id=revision.paper_id,
            arxiv_id=revision.arxiv_id,
            title=f"Category paper {index}",
            abstract=f"Real abstract {index}",
            primary_category="cs.AI",
            categories=["cs.AI"],
            pdf_url=f"https://arxiv.org/pdf/{revision.arxiv_id}",
            source_license=None,
            processing_status=ProcessingStatus.READY,
            published_at=observed_at - timedelta(days=index),
            source_updated_at=observed_at,
            author_links=[],
        )
        for index, revision in enumerate(fallback_revisions, start=1)
    ]
    paper_rows = MagicMock()
    paper_rows.all.return_value = prepared_papers
    session = MagicMock(spec=AsyncSession)
    session.scalars = AsyncMock(return_value=paper_rows)
    session.commit = AsyncMock()

    enqueue_downloads = AsyncMock(
        return_value=tuple(revision.paper_id for revision in fallback_revisions)
    )
    wait_for_papers = AsyncMock()
    digest_repository = MagicMock()
    digest_repository.create_digest = AsyncMock(
        return_value=SimpleNamespace(
            id=uuid4(),
            digest_type=DigestType.MANUAL,
            generated_at=observed_at,
        )
    )

    monkeypatch.setattr(onboarding, "ArxivClient", MagicMock(return_value=arxiv_context))
    monkeypatch.setattr(
        onboarding,
        "SemanticScholarClient",
        MagicMock(return_value=semantic_context),
    )
    monkeypatch.setattr(
        onboarding,
        "ArxivIngestionService",
        MagicMock(return_value=ingestion),
    )
    monkeypatch.setattr(
        onboarding,
        "SeedGraphCandidateService",
        MagicMock(return_value=graph_candidates),
    )
    monkeypatch.setattr(
        onboarding,
        "PreferenceRepository",
        MagicMock(return_value=preferences),
    )
    monkeypatch.setattr(onboarding, "enqueue_seed_downloads", enqueue_downloads)
    monkeypatch.setattr(onboarding, "wait_for_seed_papers", wait_for_papers)
    monkeypatch.setattr(
        onboarding,
        "DigestRepository",
        MagicMock(return_value=digest_repository),
    )

    result = asyncio.run(
        onboarding.initialize_from_seed(
            SeedInitializationRequest(arxiv_reference="1706.03762"),
            Principal(user_id=uuid4()),
            cast(TaskQueue, MagicMock()),
            cast(Settings, MagicMock(spec=Settings)),
            cast(AsyncSession, session),
        )
    )

    assert result.seed_arxiv_id == "1706.03762"
    assert result.category == "cs.AI"
    assert result.paper_count == 5
    assert {entry.paper.arxiv_id for entry in result.digest.entries} == {
        revision.arxiv_id for revision in fallback_revisions
    }
    arxiv_client.fetch_by_category.assert_awaited_once_with("cs.AI", max_results=8)
    assert ingestion.persist_feed_detailed.await_args_list == [
        call(seed_feed),
        call(category_feed),
    ]
    graph_candidates.persist.assert_not_awaited()
    enqueue_downloads.assert_awaited_once()
    enqueue_call = enqueue_downloads.await_args
    assert enqueue_call is not None
    assert enqueue_call.args[2] == fallback_revisions
    wait_for_papers.assert_awaited_once()


@pytest.mark.base
@pytest.mark.api
def test_category_fallback_reports_arxiv_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_feed = SimpleNamespace(
        records=(SimpleNamespace(primary_category="cs.AI"),),
    )
    arxiv_client = MagicMock()
    arxiv_client.fetch_by_id = AsyncMock(return_value=seed_feed)
    arxiv_client.fetch_by_category = AsyncMock(side_effect=ArxivHTTPError(503))
    arxiv_context = MagicMock()
    arxiv_context.__aenter__ = AsyncMock(return_value=arxiv_client)
    arxiv_context.__aexit__ = AsyncMock(return_value=None)

    semantic_context = MagicMock()
    semantic_context.__aenter__ = AsyncMock(return_value=MagicMock())
    semantic_context.__aexit__ = AsyncMock(return_value=None)

    ingestion = MagicMock()
    ingestion.persist_feed_detailed = AsyncMock(
        return_value=SimpleNamespace(
            revisions=(SimpleNamespace(paper_id=uuid4(), arxiv_id="1706.03762"),)
        )
    )
    graph_candidates = MagicMock()
    graph_candidates.discover = AsyncMock(
        side_effect=InsufficientSeedGraphCandidates(
            "Semantic Scholar has no matching record for the seed paper"
        )
    )

    monkeypatch.setattr(onboarding, "ArxivClient", MagicMock(return_value=arxiv_context))
    monkeypatch.setattr(
        onboarding,
        "SemanticScholarClient",
        MagicMock(return_value=semantic_context),
    )
    monkeypatch.setattr(
        onboarding,
        "ArxivIngestionService",
        MagicMock(return_value=ingestion),
    )
    monkeypatch.setattr(
        onboarding,
        "SeedGraphCandidateService",
        MagicMock(return_value=graph_candidates),
    )

    with pytest.raises(ApiError) as captured:
        asyncio.run(
            onboarding.initialize_from_seed(
                SeedInitializationRequest(arxiv_reference="1706.03762"),
                Principal(user_id=uuid4()),
                cast(TaskQueue, MagicMock()),
                cast(Settings, MagicMock(spec=Settings)),
                cast(AsyncSession, MagicMock(spec=AsyncSession)),
            )
        )

    assert captured.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert captured.value.code == "arxiv_unavailable"
    arxiv_client.fetch_by_category.assert_awaited_once_with("cs.AI", max_results=8)
