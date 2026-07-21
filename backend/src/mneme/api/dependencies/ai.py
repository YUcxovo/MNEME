"""Shared dependencies for AI endpoints."""

from typing import Annotated, Protocol

from arq import create_pool
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.budget import BudgetExceededError
from mneme.ai.embeddings import EmbeddingService, build_embedding_service
from mneme.ai.service import LLMService, build_llm_service
from mneme.ai.types import AIError, LLMProviderError, ProviderNotConfiguredError
from mneme.api.errors import ApiError
from mneme.core.config import Settings
from mneme.db.dependencies import get_session
from mneme.repositories.artifacts import ArtifactRepository
from mneme.repositories.digests import DigestRepository
from mneme.repositories.jobs import PipelineJobRepository
from mneme.repositories.qa import QaConversationRepository
from mneme.tasks.worker import create_arq_redis_settings


class TaskQueue(Protocol):
    """The narrow enqueue surface AI endpoints need from ARQ."""

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> object:
        """Queue one background job."""
        ...


def get_llm_service(request: Request) -> LLMService:
    """Return the lazily constructed application-scoped LLM service."""
    service: LLMService | None = getattr(request.app.state, "llm_service", None)
    if service is None:
        service = build_llm_service(request.app.state.settings, request.app.state.redis)
        request.app.state.llm_service = service
    return service


def get_embedding_service(request: Request) -> EmbeddingService:
    """Return the application-scoped embedding service, if configured."""
    service: EmbeddingService | None = getattr(request.app.state, "embedding_service", None)
    if service is None:
        settings: Settings = request.app.state.settings
        service = build_embedding_service(settings, request.app.state.redis)
        if service is None:
            raise ApiError(
                503,
                "ai_provider_unconfigured",
                "No embedding provider is configured.",
            )
        request.app.state.embedding_service = service
    return service


async def get_task_queue(request: Request) -> TaskQueue:
    """Return the lazily created application-scoped ARQ enqueue pool."""
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is None:
        settings: Settings = request.app.state.settings
        pool = await create_pool(
            create_arq_redis_settings(settings),
            default_queue_name=settings.arq_queue_name,
        )
        request.app.state.arq_pool = pool
    return pool


async def get_artifact_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ArtifactRepository:
    """Bind an artifact repository to the request session."""
    return ArtifactRepository(session)


async def get_pipeline_job_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> PipelineJobRepository:
    """Bind a pipeline job repository to the request session."""
    return PipelineJobRepository(session)


async def get_qa_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> QaConversationRepository:
    """Bind a Q&A conversation repository to the request session."""
    return QaConversationRepository(session)


async def get_digest_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DigestRepository:
    """Bind a digest repository to the request session."""
    return DigestRepository(session)


def map_ai_error(error: AIError) -> ApiError:
    """Translate an expected AI-layer failure into the stable error envelope."""
    if isinstance(error, BudgetExceededError):
        return ApiError(
            429,
            "ai_budget_exhausted",
            "The daily AI budget is exhausted; try again tomorrow.",
        )
    if isinstance(error, ProviderNotConfiguredError):
        return ApiError(
            503,
            "ai_provider_unconfigured",
            "No AI provider is configured for this deployment.",
        )
    if isinstance(error, LLMProviderError):
        return ApiError(
            503,
            "ai_provider_error",
            "The AI provider is temporarily unavailable.",
        )
    return ApiError(503, "ai_unavailable", "The AI service is temporarily unavailable.")
