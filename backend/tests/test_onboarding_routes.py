"""Focused tests for local-demo seed reference handling."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import ANY, AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import TaskQueue
from mneme.api.dependencies.auth import Principal
from mneme.api.errors import ApiError
from mneme.api.routes import onboarding
from mneme.api.routes.onboarding_support import normalize_arxiv_reference
from mneme.api.schemas.onboarding import SeedInitializationRequest, SeedInitializationResult
from mneme.core.config import Settings
from mneme.models.paper import ProcessingStatus
from mneme.services.arxiv.client import ArxivHTTPError
from mneme.services.seed_graph import SeedGraphMetadataUnavailable


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
def test_completed_seed_is_reloaded_after_recovery_before_external_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = MagicMock()
    stale.digest.entries = [
        SimpleNamespace(paper=SimpleNamespace(processing_status=ProcessingStatus.FAILED))
    ]
    refreshed = MagicMock()
    refreshed.digest.entries = [
        SimpleNamespace(paper=SimpleNamespace(processing_status=ProcessingStatus.READY))
    ]
    load_existing = AsyncMock(side_effect=[stale, refreshed])
    resume_existing = AsyncMock()
    arxiv_client = MagicMock()
    monkeypatch.setattr(onboarding, "_load_existing_seed", load_existing)
    monkeypatch.setattr(onboarding, "_resume_existing_seed", resume_existing)
    monkeypatch.setattr(onboarding, "ArxivClient", arxiv_client)
    principal = Principal(user_id=uuid4())
    session = cast(AsyncSession, MagicMock(spec=AsyncSession))
    queue = cast(TaskQueue, MagicMock())

    result = asyncio.run(
        onboarding.initialize_from_seed(
            SeedInitializationRequest(arxiv_reference="1706.03762v5"),
            principal,
            queue,
            Settings(_env_file=None),
            session,
        )
    )

    assert result is refreshed
    assert result.digest.entries[0].paper.processing_status is ProcessingStatus.READY
    assert load_existing.await_count == 2
    for invocation in load_existing.await_args_list:
        assert invocation.args == (session,)
        assert invocation.kwargs == {
            "user_id": principal.user_id,
            "seed_arxiv_id": "1706.03762",
        }
    resume_existing.assert_awaited_once_with(
        session,
        queue,
        stale,
        deadline=ANY,
        embedding_model="text-embedding-3-small",
        seed_arxiv_id="1706.03762",
    )
    arxiv_client.assert_not_called()
    assert onboarding._seed_generator_version("1706.03762") == ("seed-onboarding-v2:1706.03762")


@pytest.mark.base
@pytest.mark.api
def test_existing_seed_fails_closed_when_recovery_state_cannot_be_reloaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale = MagicMock()
    monkeypatch.setattr(onboarding, "_load_existing_seed", AsyncMock(side_effect=[stale, None]))
    monkeypatch.setattr(onboarding, "_resume_existing_seed", AsyncMock())
    principal = Principal(user_id=uuid4())

    with pytest.raises(ApiError) as captured:
        asyncio.run(
            onboarding.initialize_from_seed(
                SeedInitializationRequest(arxiv_reference="1706.03762"),
                principal,
                cast(TaskQueue, MagicMock()),
                Settings(_env_file=None),
                cast(AsyncSession, MagicMock(spec=AsyncSession)),
            )
        )

    assert captured.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert captured.value.code == "seed_state_incomplete"


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_existing_seed_retries_and_waits_for_ready_seed_paper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_paper_id = uuid4()
    digest_paper_ids = (uuid4(), uuid4())
    existing = SimpleNamespace(
        digest=SimpleNamespace(
            entries=[
                SimpleNamespace(paper=SimpleNamespace(id=paper_id)) for paper_id in digest_paper_ids
            ]
        )
    )
    session = AsyncMock(spec=AsyncSession)
    session.scalar.return_value = seed_paper_id
    resume = AsyncMock(return_value=1)
    wait = AsyncMock()
    monkeypatch.setattr(onboarding, "resume_failed_seed_jobs", resume)
    monkeypatch.setattr(onboarding, "wait_for_seed_papers", wait)
    queue = cast(TaskQueue, MagicMock())

    asyncio.run(
        onboarding._resume_existing_seed(
            session,
            queue,
            cast(SeedInitializationResult, existing),
            deadline=123.0,
            embedding_model="text-embedding-3-small",
            seed_arxiv_id="1706.03762",
        )
    )

    resume.assert_awaited_once_with(
        session,
        queue,
        (seed_paper_id, *digest_paper_ids),
        embedding_model="text-embedding-3-small",
    )
    wait.assert_awaited_once_with(
        session,
        (seed_paper_id, *digest_paper_ids),
        embedding_model="text-embedding-3-small",
        required_ready_ids=(seed_paper_id,),
        deadline=123.0,
    )


@pytest.mark.base
@pytest.mark.api
def test_metadata_failure_returns_retryable_error_without_category_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    arxiv_client = MagicMock()
    arxiv_client.fetch_by_id = AsyncMock(
        return_value=SimpleNamespace(
            records=(SimpleNamespace(primary_category="cs.AI"),),
        )
    )
    arxiv_client.fetch_by_category = AsyncMock()
    arxiv_context = MagicMock()
    arxiv_context.__aenter__ = AsyncMock(return_value=arxiv_client)
    arxiv_context.__aexit__ = AsyncMock(return_value=None)

    semantic_context = MagicMock()
    semantic_context.__aenter__ = AsyncMock(return_value=MagicMock())
    semantic_context.__aexit__ = AsyncMock(return_value=None)

    ingestion = MagicMock()
    ingestion.persist_feed_detailed = AsyncMock(
        return_value=SimpleNamespace(
            revisions=(SimpleNamespace(paper_id=uuid4()),),
        )
    )

    metadata_error = SeedGraphMetadataUnavailable(
        "arXiv citation-neighbor metadata remained unavailable after retry"
    )
    metadata_error.__cause__ = ArxivHTTPError(429)
    graph_candidates = MagicMock()
    graph_candidates.discover = AsyncMock(side_effect=metadata_error)
    graph_candidates.persist = AsyncMock()

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
    assert captured.value.code == "citation_metadata_unavailable"
    arxiv_client.fetch_by_category.assert_not_awaited()
    graph_candidates.persist.assert_not_awaited()
