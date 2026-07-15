"""Contract tests for the authenticated paper and preference routes."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import (
    get_paper_catalog_repository,
    get_preference_repository,
)
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.health import router as health_router
from mneme.api.routes.papers import router as papers_router
from mneme.api.routes.preferences import router as preferences_router
from mneme.models.paper import Author, Paper, PaperAuthor, ProcessingStatus
from mneme.repositories.paper_catalog import PaperPageResult
from mneme.repositories.preferences import PreferenceSnapshot

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000222")
TIMESTAMP = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)


def _paper() -> Paper:
    paper = Paper(
        id=PAPER_ID,
        arxiv_id="2607.00001",
        title="Grounded Research",
        abstract="A source-grounded abstract.",
        primary_category="cs.AI",
        categories=["cs.AI", "cs.CL"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        source_license=None,
        processing_status=ProcessingStatus.METADATA_ONLY,
        published_at=TIMESTAMP,
        source_updated_at=TIMESTAMP,
    )
    author = Author(
        id=uuid4(),
        display_name="Ada Lovelace",
        normalized_name="ada lovelace",
    )
    link = PaperAuthor(paper_id=paper.id, author_id=author.id, author_order=0)
    link.author = author
    paper.author_links = [link]
    return paper


class FakePaperCatalogRepository:
    """Configurable catalog fake for HTTP contract tests."""

    def __init__(self, paper: Paper | None) -> None:
        self.paper = paper
        self.last_limit: int | None = None

    async def list_papers(self, *, limit: int, cursor: object = None) -> PaperPageResult:
        self.last_limit = limit
        items = [self.paper] if self.paper is not None else []
        return PaperPageResult(items=items, next_cursor=None)

    async def get_paper(self, paper_id: UUID) -> Paper | None:
        if self.paper is not None and self.paper.id == paper_id:
            return self.paper
        return None


class FakePreferenceRepository:
    """Configurable preference fake that records full replacements."""

    def __init__(self, snapshot: PreferenceSnapshot | None) -> None:
        self.snapshot = snapshot
        self.last_replacement: tuple[list[str], list[str]] | None = None

    async def get_preferences(self, user_id: UUID) -> PreferenceSnapshot | None:
        assert user_id == USER_ID
        return self.snapshot

    async def replace_preferences(
        self,
        user_id: UUID,
        *,
        topics: list[str],
        followed_authors: list[str],
    ) -> PreferenceSnapshot | None:
        assert user_id == USER_ID
        self.last_replacement = (topics, followed_authors)
        return self.snapshot


def _application(
    paper_repository: FakePaperCatalogRepository,
    preference_repository: FakePreferenceRepository,
) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    async def paper_repository_override() -> FakePaperCatalogRepository:
        return paper_repository

    async def preference_repository_override() -> FakePreferenceRepository:
        return preference_repository

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(health_router, prefix="/v1")
    application.include_router(papers_router, prefix="/v1")
    application.include_router(preferences_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_paper_catalog_repository] = paper_repository_override
    application.dependency_overrides[get_preference_repository] = preference_repository_override
    return application


async def _request(
    application: FastAPI,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    json: object | None = None,
) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, headers=headers, json=json)


def _snapshot() -> PreferenceSnapshot:
    return PreferenceSnapshot(
        topics=["machine learning"],
        followed_authors=["ada lovelace"],
        model_version=2,
        updated_at=TIMESTAMP,
    )


@pytest.mark.base
@pytest.mark.api
def test_list_papers_returns_exact_public_fields() -> None:
    paper_repository = FakePaperCatalogRepository(_paper())
    application = _application(paper_repository, FakePreferenceRepository(_snapshot()))

    response = asyncio.run(_request(application, "GET", "/v1/papers?limit=10"))

    assert response.status_code == 200
    assert paper_repository.last_limit == 10
    assert response.json() == {
        "items": [
            {
                "id": str(PAPER_ID),
                "arxiv_id": "2607.00001",
                "title": "Grounded Research",
                "authors": ["Ada Lovelace"],
                "abstract": "A source-grounded abstract.",
                "primary_category": "cs.AI",
                "categories": ["cs.AI", "cs.CL"],
                "pdf_url": "https://arxiv.org/pdf/2607.00001",
                "source_license": None,
                "processing_status": "metadata_only",
                "published_at": "2026-07-15T08:30:00Z",
                "updated_at": "2026-07-15T08:30:00Z",
            }
        ],
        "next_cursor": None,
    }


@pytest.mark.base
@pytest.mark.api
def test_invalid_cursor_returns_stable_error() -> None:
    application = _application(
        FakePaperCatalogRepository(_paper()), FakePreferenceRepository(_snapshot())
    )

    response = asyncio.run(
        _request(
            application,
            "GET",
            "/v1/papers?cursor=not-a-cursor",
            headers={"X-Request-ID": "catalog-test"},
        )
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_cursor",
        "message": "The pagination cursor is invalid.",
        "request_id": "catalog-test",
    }


@pytest.mark.base
@pytest.mark.api
def test_missing_paper_returns_contract_error() -> None:
    application = _application(
        FakePaperCatalogRepository(None), FakePreferenceRepository(_snapshot())
    )

    response = asyncio.run(_request(application, "GET", f"/v1/papers/{uuid4()}"))

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"


@pytest.mark.base
@pytest.mark.api
def test_preferences_get_and_put_use_authenticated_user() -> None:
    preference_repository = FakePreferenceRepository(_snapshot())
    application = _application(FakePaperCatalogRepository(_paper()), preference_repository)

    get_response = asyncio.run(_request(application, "GET", "/v1/users/me/preferences"))
    put_response = asyncio.run(
        _request(
            application,
            "PUT",
            "/v1/users/me/preferences",
            json={
                "topics": [" Machine Learning ", "MACHINE LEARNING"],
                "followed_authors": [" Ada Lovelace "],
            },
        )
    )

    assert get_response.status_code == 200
    assert get_response.json() == {
        "topics": ["machine learning"],
        "followed_authors": ["ada lovelace"],
        "model_version": 2,
        "updated_at": "2026-07-15T08:30:00Z",
    }
    assert put_response.status_code == 200
    assert preference_repository.last_replacement == (
        ["machine learning"],
        ["ada lovelace"],
    )


@pytest.mark.base
@pytest.mark.api
def test_missing_demo_user_returns_contract_error() -> None:
    application = _application(FakePaperCatalogRepository(_paper()), FakePreferenceRepository(None))

    response = asyncio.run(_request(application, "GET", "/v1/users/me/preferences"))

    assert response.status_code == 404
    assert response.json()["code"] == "user_not_found"


@pytest.mark.base
@pytest.mark.api
def test_catalog_openapi_matches_frozen_paths_and_operation_ids() -> None:
    application = _application(
        FakePaperCatalogRepository(_paper()), FakePreferenceRepository(_snapshot())
    )

    schema = application.openapi()
    list_operation = schema["paths"]["/v1/papers"]["get"]

    assert list_operation["operationId"] == "listPapers"
    assert [parameter["name"] for parameter in list_operation["parameters"]] == [
        "cursor",
        "limit",
    ]
    assert schema["paths"]["/v1/papers/{paper_id}"]["get"]["operationId"] == "getPaper"
    preferences_path = schema["paths"]["/v1/users/me/preferences"]
    assert preferences_path["get"]["operationId"] == "getPreferences"
    assert preferences_path["put"]["operationId"] == "updatePreferences"
    assert list_operation["security"] == [{"demoToken": []}]
    assert preferences_path["get"]["security"] == [{"demoToken": []}]
    assert preferences_path["put"]["security"] == [{"demoToken": []}]
    assert "security" not in schema["paths"]["/v1/health"]["get"]
    updated_at_schema = schema["components"]["schemas"]["Preferences"]["properties"]["updated_at"]
    assert updated_at_schema["type"] == "string"
    assert updated_at_schema["format"] == "date-time"
    assert "anyOf" not in updated_at_schema
