"""Shared dependencies for AI endpoints."""

from typing import Annotated, Protocol

from arq import create_pool
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.budget import BudgetGuard
from mneme.ai.embeddings import EmbeddingService, OpenAIEmbeddingProvider
from mneme.ai.service import LLMService, build_llm_service
from mneme.api.errors import ApiError
from mneme.core.config import Settings
from mneme.db.dependencies import get_session
from mneme.repositories.artifacts import ArtifactRepository
from mneme.repositories.jobs import PipelineJobRepository
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
        if settings.openai_api_key is None:
            raise ApiError(
                503,
                "ai_provider_unconfigured",
                "No embedding provider is configured.",
            )
        service = EmbeddingService(
            provider=OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout_seconds=settings.llm_timeout_seconds,
            ),
            budget=BudgetGuard(
                request.app.state.redis, daily_cap_usd=settings.ai_daily_budget_usd
            ),
            model=settings.ai_embedding_model,
            batch_size=settings.ai_embedding_batch_size,
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
