"""Focused tests for local-demo seed reference handling."""

import asyncio
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock
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
def test_completed_seed_is_reused_before_external_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = MagicMock()
    load_existing = AsyncMock(return_value=expected)
    arxiv_client = MagicMock()
    monkeypatch.setattr(onboarding, "_load_existing_seed", load_existing)
    monkeypatch.setattr(onboarding, "ArxivClient", arxiv_client)
    principal = Principal(user_id=uuid4())
    session = cast(AsyncSession, MagicMock(spec=AsyncSession))

    result = asyncio.run(
        onboarding.initialize_from_seed(
            SeedInitializationRequest(arxiv_reference="1706.03762v5"),
            principal,
            cast(TaskQueue, MagicMock()),
            Settings(_env_file=None),
            session,
        )
    )

    assert result is expected
    load_existing.assert_awaited_once_with(
        session,
        user_id=principal.user_id,
        seed_arxiv_id="1706.03762",
    )
    arxiv_client.assert_not_called()
    assert onboarding._seed_generator_version("1706.03762") == ("seed-onboarding-v2:1706.03762")


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
