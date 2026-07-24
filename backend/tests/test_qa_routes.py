"""Contract tests for POST /qa/ask."""

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import UUID, uuid4

import pytest
from conftest import FakeRedis
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from redis.asyncio import Redis

from mneme.ai.budget import BudgetGuard
from mneme.ai.cache import LLMCache
from mneme.ai.embeddings import EmbeddingService, FakeEmbeddingProvider
from mneme.ai.providers import LLMProvider
from mneme.ai.providers.fake import FakeLLMProvider
from mneme.ai.routing import ModelRouter
from mneme.ai.service import LLMService
from mneme.ai.types import AITask, LLMProviderError, ProviderName
from mneme.api.dependencies.ai import (
    get_artifact_repository,
    get_embedding_service,
    get_llm_service,
    get_qa_repository,
)
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.qa import get_request_settings
from mneme.api.routes.qa import router as qa_router
from mneme.core.config import Settings
from mneme.db.dependencies import get_session
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.models.qa import QaConversation, QaMessage
from mneme.repositories.qa import ConversationMismatchError

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000222")
PAPER_VERSION_ID = UUID("00000000-0000-0000-0000-000000000333")
CONVERSATION_ID = UUID("00000000-0000-0000-0000-000000000444")
TIMESTAMP = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)


def _paper() -> Paper:
    return Paper(
        id=PAPER_ID,
        arxiv_id="2607.00001",
        title="Grounded Research",
        abstract="An abstract.",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        source_license=None,
        processing_status=ProcessingStatus.READY,
        published_at=TIMESTAMP,
        source_updated_at=TIMESTAMP,
    )


class FakeChunkRow:
    def __init__(self) -> None:
        self.id = uuid4()
        self.paper_id = PAPER_ID
        self.chunk_index = 0
        self.section_title = "Model Architecture"
        self.content = "The transformer uses multi-head attention instead of recurrence"
        self.page_start = 2
        self.page_end = 3


class FakePaperCatalogRepository:
    def __init__(self, paper: Paper | None) -> None:
        self.paper = paper

    async def get_paper(self, paper_id: UUID) -> Paper | None:
        if self.paper is not None and self.paper.id == paper_id:
            return self.paper
        return None


class FakeArtifactRepository:
    def __init__(
        self,
        rows: list[tuple[FakeChunkRow, float]],
        *,
        paper_version_id: UUID | None = PAPER_VERSION_ID,
    ) -> None:
        self.rows = rows
        self.version = (
            PaperVersion(id=paper_version_id, paper_id=PAPER_ID, version_number=1)
            if paper_version_id is not None
            else None
        )
        self.queries: list[tuple[UUID, UUID, int]] = []

    async def get_latest_version(self, paper_id: UUID) -> PaperVersion | None:
        if self.version is not None and self.version.paper_id == paper_id:
            return self.version
        return None

    async def search_chunks(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        query_embedding: tuple[float, ...],
        limit: int,
    ) -> list[tuple[FakeChunkRow, float]]:
        self.queries.append((paper_id, paper_version_id, limit))
        return self.rows[:limit]

    async def get_context_anchor_chunks(
        self,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        query_embedding: tuple[float, ...],
        limit: int,
    ) -> list[tuple[FakeChunkRow, float]]:
        del paper_id, paper_version_id, query_embedding
        return self.rows[:limit]


class FakeQaRepository:
    def __init__(self, *, mismatch: bool = False) -> None:
        self.mismatch = mismatch
        self.exchanges: list[tuple[QaConversation, str, QaMessage]] = []

    async def resolve_conversation(
        self, *, conversation_id: UUID | None, user_id: UUID, paper_id: UUID
    ) -> QaConversation:
        if self.mismatch:
            raise ConversationMismatchError("mismatch")
        return QaConversation(id=CONVERSATION_ID, user_id=user_id, paper_id=paper_id)

    async def append_exchange(
        self, *, conversation: QaConversation, question: str, answer: QaMessage
    ) -> QaMessage:
        self.exchanges.append((conversation, question, answer))
        return answer


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _llm_service(provider: FakeLLMProvider, *, daily_cap_usd: Decimal = Decimal("5")) -> LLMService:
    redis = cast(Redis, FakeRedis())
    return LLMService(
        router=ModelRouter({AITask.SUMMARIZE: "claude-haiku-4-5", AITask.QA: "claude-haiku-4-5"}),
        providers={ProviderName.ANTHROPIC: cast(LLMProvider, provider)},
        cache=LLMCache(
            redis, enabled=True, ttl_seconds={AITask.SUMMARIZE: 604800, AITask.QA: 86400}
        ),
        budget=BudgetGuard(redis, daily_cap_usd=daily_cap_usd),
    )


def _embedding_service(*, daily_cap_usd: Decimal = Decimal("5")) -> EmbeddingService:
    return EmbeddingService(
        provider=FakeEmbeddingProvider(),
        budget=BudgetGuard(cast(Redis, FakeRedis()), daily_cap_usd=daily_cap_usd),
        model="text-embedding-3-small",
        batch_size=8,
    )


def _application(
    *,
    catalog: FakePaperCatalogRepository,
    artifacts: FakeArtifactRepository,
    qa_repository: FakeQaRepository,
    provider: FakeLLMProvider,
    llm_cap_usd: Decimal = Decimal("5"),
    embedding_cap_usd: Decimal = Decimal("5"),
) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    async def catalog_override() -> FakePaperCatalogRepository:
        return catalog

    async def artifacts_override() -> FakeArtifactRepository:
        return artifacts

    async def qa_override() -> FakeQaRepository:
        return qa_repository

    async def llm_override() -> LLMService:
        return llm

    async def embedder_override() -> EmbeddingService:
        return embedder

    async def settings_override() -> Settings:
        return settings

    async def session_override() -> FakeSession:
        return FakeSession()

    llm = _llm_service(provider, daily_cap_usd=llm_cap_usd)
    embedder = _embedding_service(daily_cap_usd=embedding_cap_usd)
    settings = Settings(environment="testing")

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(qa_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_paper_catalog_repository] = catalog_override
    application.dependency_overrides[get_artifact_repository] = artifacts_override
    application.dependency_overrides[get_qa_repository] = qa_override
    application.dependency_overrides[get_llm_service] = llm_override
    application.dependency_overrides[get_embedding_service] = embedder_override
    application.dependency_overrides[get_request_settings] = settings_override
    application.dependency_overrides[get_session] = session_override
    return application


async def _post(application: FastAPI, payload: dict) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/qa/ask", json=payload)


@pytest.mark.base
@pytest.mark.api
@pytest.mark.rag
def test_grounded_answer_matches_frozen_contract() -> None:
    qa_repository = FakeQaRepository()
    artifacts = FakeArtifactRepository([(FakeChunkRow(), 0.9)])
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=artifacts,
        qa_repository=qa_repository,
        provider=FakeLLMProvider(
            default_response="The model replaces recurrence with multi-head attention [1]."
        ),
    )

    response = asyncio.run(
        _post(application, {"question": "What replaces recurrence?", "paper_id": str(PAPER_ID)})
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["conversation_id"] == str(CONVERSATION_ID)
    assert payload["source_match_status"] == "matched"
    assert len(payload["citations"]) == 1
    citation = payload["citations"][0]
    assert citation["paper_id"] == str(PAPER_ID)
    assert citation["section_title"] == "Model Architecture"
    assert citation["source_match"] is True
    assert len(qa_repository.exchanges) == 1
    assert artifacts.queries == [(PAPER_ID, PAPER_VERSION_ID, 8)]


@pytest.mark.base
@pytest.mark.api
@pytest.mark.rag
def test_paper_without_chunks_returns_stable_refusal() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([]),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(),
    )

    response = asyncio.run(_post(application, {"question": "Anything?", "paper_id": str(PAPER_ID)}))

    assert response.status_code == 200
    payload = response.json()
    assert payload["source_match_status"] == "insufficient_evidence"
    assert payload["citations"] == []


@pytest.mark.base
@pytest.mark.api
def test_unknown_paper_returns_not_found() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(None),
        artifacts=FakeArtifactRepository([]),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(),
    )

    response = asyncio.run(_post(application, {"question": "Anything?", "paper_id": str(uuid4())}))

    assert response.status_code == 404
    assert response.json()["code"] == "paper_not_found"


@pytest.mark.base
@pytest.mark.api
def test_paper_without_observed_revision_returns_conflict() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([], paper_version_id=None),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(),
    )

    response = asyncio.run(_post(application, {"question": "Anything?", "paper_id": str(PAPER_ID)}))

    assert response.status_code == 409
    assert response.json()["code"] == "paper_not_ready"


@pytest.mark.base
@pytest.mark.api
def test_mismatched_conversation_returns_not_found() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([]),
        qa_repository=FakeQaRepository(mismatch=True),
        provider=FakeLLMProvider(),
    )

    response = asyncio.run(
        _post(
            application,
            {
                "question": "Anything?",
                "paper_id": str(PAPER_ID),
                "conversation_id": str(uuid4()),
            },
        )
    )

    assert response.status_code == 404
    assert response.json()["code"] == "conversation_not_found"


@pytest.mark.base
@pytest.mark.api
def test_provider_failure_maps_to_stable_ai_error() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([(FakeChunkRow(), 0.9)]),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(error=LLMProviderError("boom", retryable=True)),
    )

    response = asyncio.run(
        _post(application, {"question": "What replaces recurrence?", "paper_id": str(PAPER_ID)})
    )

    assert response.status_code == 503
    assert response.json()["code"] == "ai_provider_error"


@pytest.mark.base
@pytest.mark.api
def test_exhausted_llm_budget_returns_stable_429() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([(FakeChunkRow(), 0.9)]),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(),
        llm_cap_usd=Decimal("0"),
    )

    response = asyncio.run(
        _post(application, {"question": "What replaces recurrence?", "paper_id": str(PAPER_ID)})
    )

    assert response.status_code == 429
    assert response.json()["code"] == "ai_budget_exhausted"


@pytest.mark.base
@pytest.mark.api
def test_exhausted_embedding_budget_returns_stable_429() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([(FakeChunkRow(), 0.9)]),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(),
        embedding_cap_usd=Decimal("0"),
    )

    response = asyncio.run(
        _post(application, {"question": "What replaces recurrence?", "paper_id": str(PAPER_ID)})
    )

    assert response.status_code == 429
    assert response.json()["code"] == "ai_budget_exhausted"


@pytest.mark.base
@pytest.mark.api
def test_overlong_question_fails_validation() -> None:
    application = _application(
        catalog=FakePaperCatalogRepository(_paper()),
        artifacts=FakeArtifactRepository([]),
        qa_repository=FakeQaRepository(),
        provider=FakeLLMProvider(),
    )

    response = asyncio.run(_post(application, {"question": "x" * 501, "paper_id": str(PAPER_ID)}))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
