"""Contract tests for POST /digests/recommended."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.ai import get_digest_repository
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.digests import get_request_settings
from mneme.api.routes.digests import router as digests_router
from mneme.core.config import Settings
from mneme.db.dependencies import get_session
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.paper import Paper, ProcessingStatus
from mneme.models.user import UserPreference

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
NOW = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _paper(title: str, *, age_days: float) -> Paper:
    return Paper(
        id=uuid4(),
        arxiv_id=f"2607.{uuid4().int % 100000:05d}",
        title=title,
        abstract="An abstract.",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        source_license=None,
        processing_status=ProcessingStatus.READY,
        published_at=NOW - timedelta(days=age_days),
        source_updated_at=NOW,
    )


class FakeDigestRepository:
    """In-memory digest repository driving the recommendation service."""

    def __init__(
        self,
        *,
        papers: list[Paper],
        preferences: UserPreference | None,
        fresh: Digest | None = None,
    ) -> None:
        self.papers = papers
        self.preferences = preferences
        self.fresh = fresh
        self.created: list[Digest] = []

    async def get_fresh_recommended_digest(self, *, user_id: UUID, max_age) -> Digest | None:
        return self.fresh

    async def get_preferences(self, user_id: UUID) -> UserPreference | None:
        return self.preferences

    async def list_recent_candidates(self, *, since, limit: int) -> list[Paper]:
        return self.papers[:limit]

    async def mean_chunk_embeddings(self, paper_ids):
        return {}

    async def create_digest(
        self,
        *,
        user_id: UUID,
        digest_type: DigestType,
        preference_model_version: int,
        generator_version: str,
        entries: list[DigestEntry],
    ) -> Digest:
        digest = Digest(
            id=uuid4(),
            user_id=user_id,
            digest_type=digest_type,
            generated_at=NOW,
            preference_model_version=preference_model_version,
            generator_version=generator_version,
        )
        for entry in entries:
            entry.digest_id = digest.id
        self.created.append(digest)
        return digest


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _application(repository: FakeDigestRepository) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(digests_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_digest_repository] = lambda: repository
    application.dependency_overrides[get_request_settings] = lambda: Settings(environment="testing")
    application.dependency_overrides[get_session] = lambda: FakeSession()
    return application


async def _post(application: FastAPI) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/digests/recommended")


@pytest.mark.base
@pytest.mark.api
def test_generated_digest_matches_frozen_contract() -> None:
    papers = [
        _paper("Attention transformers revisited", age_days=1),
        _paper("A survey of unrelated things", age_days=2),
    ]
    preferences = UserPreference(
        user_id=USER_ID,
        explicit_topics=["attention"],
        followed_authors=[],
        model_version=3,
    )
    repository = FakeDigestRepository(papers=papers, preferences=preferences)
    application = _application(repository)

    response = asyncio.run(_post(application))

    assert response.status_code == 200
    payload = response.json()
    assert payload["digest_type"] == "manual"
    assert len(payload["entries"]) == 2
    first = payload["entries"][0]
    assert first["rank"] == 1
    assert 0 <= first["relevance_score"] <= 1
    assert first["recommendation_reason"]
    assert first["paper"]["title"] == "Attention transformers revisited"
    assert repository.created[0].preference_model_version == 3


@pytest.mark.base
@pytest.mark.api
def test_topic_matching_paper_outranks_unrelated_one() -> None:
    papers = [
        _paper("A survey of unrelated things", age_days=1),
        _paper("Attention transformers revisited", age_days=1),
    ]
    preferences = UserPreference(
        user_id=USER_ID, explicit_topics=["attention"], followed_authors=[], model_version=1
    )
    application = _application(FakeDigestRepository(papers=papers, preferences=preferences))

    response = asyncio.run(_post(application))

    entries = response.json()["entries"]
    assert entries[0]["paper"]["title"] == "Attention transformers revisited"
    assert "attention" in entries[0]["recommendation_reason"]


@pytest.mark.base
@pytest.mark.api
def test_cold_start_user_without_preferences_still_gets_a_digest() -> None:
    application = _application(
        FakeDigestRepository(papers=[_paper("Anything recent", age_days=0.5)], preferences=None)
    )

    response = asyncio.run(_post(application))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["recommendation_reason"]


@pytest.mark.base
@pytest.mark.api
def test_empty_candidate_pool_returns_empty_digest() -> None:
    application = _application(FakeDigestRepository(papers=[], preferences=None))

    response = asyncio.run(_post(application))

    assert response.status_code == 200
    assert response.json()["entries"] == []
