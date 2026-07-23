"""Contract tests for persisted and recommended digest endpoints."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import cast
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
from mneme.repositories.digests import (
    DigestCursor,
    DigestPageResult,
    DigestRepository,
    encode_digest_cursor,
)
from mneme.services.recommendation import RecommendedDigestService

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
        digests: list[Digest] | None = None,
        next_cursor: str | None = None,
        embeddings: dict[UUID, tuple[float, ...]] | None = None,
    ) -> None:
        self.papers = papers
        self.preferences = preferences
        self.fresh = fresh
        self.digests = digests if digests is not None else []
        self.next_cursor = next_cursor
        self.created: list[Digest] = []
        self.list_calls: list[tuple[UUID, int, DigestCursor | None]] = []
        self.candidate_calls: list[tuple[datetime, datetime | None, int]] = []
        self.embeddings = embeddings or {}
        self.embedding_calls: list[tuple[list[UUID], str]] = []
        self.operation_calls: list[str] = []

    async def lock_user(self, user_id: UUID) -> None:
        assert user_id == USER_ID
        self.operation_calls.append("lock")

    async def list_digests(
        self,
        *,
        user_id: UUID,
        limit: int,
        cursor: DigestCursor | None = None,
    ) -> DigestPageResult:
        self.list_calls.append((user_id, limit, cursor))
        return DigestPageResult(items=self.digests, next_cursor=self.next_cursor)

    async def get_fresh_recommended_digest(self, *, user_id: UUID, max_age) -> Digest | None:
        self.operation_calls.append("fresh")
        return self.fresh

    async def get_preferences(self, user_id: UUID) -> UserPreference | None:
        self.operation_calls.append("preferences")
        return self.preferences

    async def list_recent_candidates(
        self, *, since: datetime, limit: int, before: datetime | None = None
    ) -> list[Paper]:
        self.candidate_calls.append((since, before, limit))
        return self.papers[:limit]

    async def mean_chunk_embeddings(
        self,
        paper_ids: list[UUID],
        *,
        embedding_model: str,
    ) -> dict[UUID, tuple[float, ...]]:
        self.embedding_calls.append((paper_ids, embedding_model))
        return self.embeddings

    async def create_digest(
        self,
        *,
        user_id: UUID,
        digest_type: DigestType,
        preference_model_version: int,
        generator_version: str,
        entries: list[DigestEntry],
    ) -> Digest:
        self.operation_calls.append("create")
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

    async def repository_override() -> FakeDigestRepository:
        return repository

    async def settings_override() -> Settings:
        return Settings(environment="testing")

    async def session_override() -> FakeSession:
        return FakeSession()

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(digests_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_digest_repository] = repository_override
    application.dependency_overrides[get_request_settings] = settings_override
    application.dependency_overrides[get_session] = session_override
    return application


async def _post(application: FastAPI) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/digests/recommended")


async def _get(
    application: FastAPI,
    path: str,
    *,
    headers: dict[str, str] | None = None,
) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path, headers=headers)


def _stored_digest() -> Digest:
    paper = _paper("A persisted paper", age_days=1)
    digest = Digest(
        id=uuid4(),
        user_id=USER_ID,
        digest_type=DigestType.WEEKLY,
        generated_at=NOW,
        preference_model_version=2,
        generator_version="test-v1",
    )
    entry = DigestEntry(
        digest_id=digest.id,
        paper_id=paper.id,
        rank=1,
        relevance_score=0.75,
        recommendation_reason="Matches your attention topic.",
    )
    entry.paper = paper
    digest.entries = [entry]
    return digest


@pytest.mark.base
@pytest.mark.api
def test_list_digests_returns_authenticated_user_page() -> None:
    digest = _stored_digest()
    next_cursor = encode_digest_cursor(NOW, digest.id)
    repository = FakeDigestRepository(
        papers=[],
        preferences=None,
        digests=[digest],
        next_cursor=next_cursor,
    )
    application = _application(repository)

    response = asyncio.run(_get(application, "/v1/digests?limit=10"))

    assert response.status_code == 200
    assert repository.list_calls == [(USER_ID, 10, None)]
    payload = response.json()
    assert payload["next_cursor"] == next_cursor
    assert payload["items"] == [
        {
            "id": str(digest.id),
            "digest_type": "weekly",
            "generated_at": "2026-07-17T12:00:00Z",
            "entries": [
                {
                    "paper": {
                        "id": str(digest.entries[0].paper.id),
                        "arxiv_id": digest.entries[0].paper.arxiv_id,
                        "title": "A persisted paper",
                        "authors": [],
                        "abstract": "An abstract.",
                        "primary_category": "cs.AI",
                        "categories": ["cs.AI"],
                        "pdf_url": "https://arxiv.org/pdf/2607.00001",
                        "source_license": None,
                        "processing_status": "ready",
                        "published_at": "2026-07-16T12:00:00Z",
                        "updated_at": "2026-07-17T12:00:00Z",
                    },
                    "rank": 1,
                    "relevance_score": 0.75,
                    "recommendation_reason": "Matches your attention topic.",
                }
            ],
        }
    ]


@pytest.mark.base
@pytest.mark.api
def test_list_digests_decodes_cursor_before_repository_query() -> None:
    digest_id = uuid4()
    cursor = encode_digest_cursor(NOW, digest_id)
    repository = FakeDigestRepository(papers=[], preferences=None)

    response = asyncio.run(_get(_application(repository), f"/v1/digests?cursor={cursor}"))

    assert response.status_code == 200
    _, limit, decoded_cursor = repository.list_calls[0]
    assert limit == 20
    assert decoded_cursor is not None
    assert decoded_cursor.generated_at == NOW
    assert decoded_cursor.digest_id == digest_id


@pytest.mark.base
@pytest.mark.api
def test_invalid_digest_cursor_returns_stable_error() -> None:
    repository = FakeDigestRepository(papers=[], preferences=None)

    response = asyncio.run(
        _get(
            _application(repository),
            "/v1/digests?cursor=not-a-cursor",
            headers={"X-Request-ID": "digest-test"},
        )
    )

    assert response.status_code == 400
    assert response.json() == {
        "code": "invalid_cursor",
        "message": "The pagination cursor is invalid.",
        "request_id": "digest-test",
    }
    assert repository.list_calls == []


@pytest.mark.base
@pytest.mark.api
def test_digest_list_openapi_matches_frozen_contract() -> None:
    application = _application(FakeDigestRepository(papers=[], preferences=None))

    schema = application.openapi()
    operation = schema["paths"]["/v1/digests"]["get"]

    assert operation["operationId"] == "listDigests"
    assert [parameter["name"] for parameter in operation["parameters"]] == ["cursor", "limit"]
    assert operation["security"] == [{"demoToken": []}]
    assert schema["paths"]["/v1/digests/recommended"]["post"]["operationId"] == (
        "generateRecommendedDigest"
    )
    assert "202" in schema["paths"]["/v1/digests/recommended"]["post"]["responses"]


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
    assert repository.operation_calls == ["lock", "fresh", "preferences", "create"]


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
    repository = FakeDigestRepository(
        papers=[_paper("Anything recent", age_days=0.5)],
        preferences=None,
    )
    application = _application(repository)

    response = asyncio.run(_post(application))

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["recommendation_reason"]
    assert repository.embedding_calls == []


@pytest.mark.base
@pytest.mark.api
def test_empty_candidate_pool_returns_empty_digest() -> None:
    application = _application(FakeDigestRepository(papers=[], preferences=None))

    response = asyncio.run(_post(application))

    assert response.status_code == 200
    assert response.json()["entries"] == []


@pytest.mark.base
@pytest.mark.rag
def test_weekly_generation_uses_an_exclusive_period_cutoff() -> None:
    repository = FakeDigestRepository(
        papers=[_paper("Weekly paper", age_days=1)],
        preferences=None,
    )
    service = RecommendedDigestService(
        cast(DigestRepository, repository), candidate_days=14, max_entries=10
    )

    bundle = asyncio.run(
        service.generate(
            USER_ID,
            digest_type=DigestType.WEEKLY,
            as_of=NOW,
        )
    )

    assert bundle.digest.digest_type is DigestType.WEEKLY
    assert len(bundle.entries) == 1
    assert repository.candidate_calls == [(NOW - timedelta(days=14), NOW, 200)]
    assert repository.operation_calls == ["lock", "preferences", "create"]


@pytest.mark.base
@pytest.mark.rag
def test_fresh_manual_digest_is_read_while_holding_user_lock() -> None:
    fresh = _stored_digest()
    repository = FakeDigestRepository(papers=[], preferences=None, fresh=fresh)
    service = RecommendedDigestService(
        cast(DigestRepository, repository), candidate_days=14, max_entries=10
    )

    bundle = asyncio.run(service.get_or_generate(USER_ID))

    assert bundle.digest is fresh
    assert repository.created == []
    assert repository.operation_calls == ["lock", "fresh"]


@pytest.mark.base
@pytest.mark.rag
def test_behavior_recommendations_request_only_the_matching_embedding_model() -> None:
    paper = _paper("Behavior match", age_days=1)
    preferences = UserPreference(
        user_id=USER_ID,
        explicit_topics=[],
        followed_authors=[],
        behavior_embedding=[1.0, 0.0],
        behavior_embedding_model="embedding-test-v1",
        model_version=1,
    )
    repository = FakeDigestRepository(
        papers=[paper],
        preferences=preferences,
        embeddings={paper.id: (1.0, 0.0)},
    )
    service = RecommendedDigestService(
        cast(DigestRepository, repository), candidate_days=14, max_entries=10
    )

    bundle = asyncio.run(
        service.generate(
            USER_ID,
            digest_type=DigestType.MANUAL,
            as_of=NOW,
        )
    )

    assert repository.embedding_calls == [([paper.id], "embedding-test-v1")]
    assert bundle.entries[0].relevance_score > 0


@pytest.mark.base
@pytest.mark.rag
def test_digest_cutoff_must_be_timezone_aware() -> None:
    repository = FakeDigestRepository(papers=[], preferences=None)
    service = RecommendedDigestService(
        cast(DigestRepository, repository), candidate_days=14, max_entries=10
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        asyncio.run(
            service.generate(
                USER_ID,
                digest_type=DigestType.WEEKLY,
                as_of=datetime(2026, 7, 20),
            )
        )
