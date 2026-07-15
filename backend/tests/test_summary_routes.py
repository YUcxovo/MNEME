"""Contract tests for the Milestone 1 mock summary endpoint."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.summaries import router as summaries_router
from mneme.models.paper import Paper, ProcessingStatus

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000222")
TIMESTAMP = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)
ABSTRACT = (
    "We introduce a grounded assistant. It cites sources for every claim. "
    "Extensive experiments show strong results."
)


def _paper() -> Paper:
    return Paper(
        id=PAPER_ID,
        arxiv_id="2607.00001",
        title="Grounded Research",
        abstract=ABSTRACT,
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        source_license=None,
        processing_status=ProcessingStatus.METADATA_ONLY,
        published_at=TIMESTAMP,
        source_updated_at=TIMESTAMP,
    )


class FakePaperCatalogRepository:
    """Single-paper catalog fake."""

    def __init__(self, paper: Paper | None) -> None:
        self.paper = paper

    async def get_paper(self, paper_id: UUID) -> Paper | None:
        if self.paper is not None and self.paper.id == paper_id:
            return self.paper
        return None


def _application(repository: FakePaperCatalogRepository) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    async def repository_override() -> FakePaperCatalogRepository:
        return repository

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(summaries_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_paper_catalog_repository] = repository_override
    return application


async def _get(application: FastAPI, path: str) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.base
@pytest.mark.api
def test_summary_returns_frozen_contract_fields() -> None:
    application = _application(FakePaperCatalogRepository(_paper()))

    response = asyncio.run(_get(application, f"/v1/papers/{PAPER_ID}/summary"))

    assert response.status_code == 200
    assert response.json() == {
        "paper_id": str(PAPER_ID),
        "status": "partial",
        "tldr": ("We introduce a grounded assistant. It cites sources for every claim."),
        "key_claims": [],
        "methodology": None,
        "limitations": None,
        "source_match_status": "not_checked",
    }


@pytest.mark.base
@pytest.mark.api
def test_unknown_paper_returns_stable_not_found_error() -> None:
    application = _application(FakePaperCatalogRepository(None))

    response = asyncio.run(_get(application, f"/v1/papers/{uuid4()}/summary"))

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "paper_not_found"
    assert "request_id" in payload
