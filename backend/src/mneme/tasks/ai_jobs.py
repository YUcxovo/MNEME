"""ARQ job functions for the AI pipeline stages (summarize, chunk, embed).

Wrappers stay thin: they open one session per run, delegate to the stage
functions in ``mneme.ai.pipeline``, record durable job state, and translate
AI-layer failures into stable error codes. Retryable provider errors are
re-raised so ARQ's retry policy applies; terminal failures are swallowed
after being recorded (retrying cannot fix them).
"""

from typing import Any
from uuid import UUID

import structlog

from mneme.ai.budget import BudgetExceededError
from mneme.ai.chunking import ParsedSection
from mneme.ai.pipeline import (
    PaperNotReadyError,
    chunk_paper_stage,
    embed_chunks_stage,
    summarize_paper_stage,
)
from mneme.ai.types import LLMProviderError, ProviderNotConfiguredError
from mneme.core.config import Settings
from mneme.repositories.jobs import PipelineJobRepository

logger = structlog.get_logger(__name__)


def _job_uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


async def _run_stage(
    ctx: dict[str, Any],
    *,
    stage_name: str,
    job_id: str | None,
    paper_id: str,
    runner,
) -> str:
    """Shared job harness: session scope, job bookkeeping, error mapping."""
    database = ctx["database"]
    resolved_job_id = _job_uuid(job_id)
    async with database.session_factory() as session:
        jobs = PipelineJobRepository(session)
        if resolved_job_id is not None:
            await jobs.mark_running(resolved_job_id)
            await session.commit()
        try:
            outcome = await runner(session)
            await session.commit()
        except BudgetExceededError as error:
            await session.rollback()
            if resolved_job_id is not None:
                await jobs.mark_failed(
                    resolved_job_id, error_code="ai_budget_exhausted", message=str(error)
                )
                await session.commit()
            logger.warning("stage_budget_exhausted", stage=stage_name, paper_id=paper_id)
            return "budget_exhausted"
        except ProviderNotConfiguredError as error:
            await session.rollback()
            if resolved_job_id is not None:
                await jobs.mark_failed(
                    resolved_job_id, error_code="ai_provider_unconfigured", message=str(error)
                )
                await session.commit()
            logger.error("stage_provider_unconfigured", stage=stage_name, paper_id=paper_id)
            return "provider_unconfigured"
        except LLMProviderError as error:
            await session.rollback()
            if resolved_job_id is not None:
                await jobs.mark_failed(
                    resolved_job_id, error_code="ai_provider_error", message=str(error)
                )
                await session.commit()
            if error.retryable:
                raise
            logger.error("stage_provider_failed", stage=stage_name, paper_id=paper_id)
            return "provider_error"
        except PaperNotReadyError as error:
            await session.rollback()
            if resolved_job_id is not None:
                await jobs.mark_failed(
                    resolved_job_id, error_code="paper_not_ready", message=str(error)
                )
                await session.commit()
            logger.warning("stage_paper_not_ready", stage=stage_name, paper_id=paper_id)
            return "paper_not_ready"

        if resolved_job_id is not None:
            await jobs.mark_succeeded(resolved_job_id)
            await session.commit()
        logger.info("stage_completed", stage=stage_name, paper_id=paper_id, outcome=outcome)
        return "ok"


async def summarize_paper(
    ctx: dict[str, Any],
    paper_id: str,
    *,
    job_id: str | None = None,
    body: str | None = None,
) -> str:
    """Generate and store the structured summary for one paper."""

    async def runner(session):
        summary = await summarize_paper_stage(
            session,
            paper_id=UUID(paper_id),
            summarizer=ctx["summarizer"],
            body=body,
        )
        return summary.status.value

    return await _run_stage(
        ctx, stage_name="summarize_paper", job_id=job_id, paper_id=paper_id, runner=runner
    )


async def chunk_paper(
    ctx: dict[str, Any],
    paper_id: str,
    sections: list[dict[str, Any]],
    *,
    job_id: str | None = None,
) -> str:
    """Chunk parsed sections and enqueue embedding for the stored chunks."""
    settings: Settings = ctx["settings"]
    parsed = [ParsedSection.model_validate(section) for section in sections]

    async def runner(session):
        return await chunk_paper_stage(
            session,
            paper_id=UUID(paper_id),
            sections=parsed,
            max_tokens=settings.ai_chunk_max_tokens,
            overlap_tokens=settings.ai_chunk_overlap_tokens,
        )

    outcome = await _run_stage(
        ctx, stage_name="chunk_paper", job_id=job_id, paper_id=paper_id, runner=runner
    )
    queue = ctx.get("redis")
    if outcome == "ok" and queue is not None:
        await queue.enqueue_job("embed_chunks", paper_id, _job_id=f"embed_chunks:{paper_id}")
    return outcome


async def embed_chunks(
    ctx: dict[str, Any],
    paper_id: str,
    *,
    job_id: str | None = None,
) -> str:
    """Embed every unembedded chunk of one paper."""

    async def runner(session):
        embedder = ctx.get("embedder")
        if embedder is None:
            raise ProviderNotConfiguredError(
                "No embedding provider is configured (missing OpenAI API key)."
            )
        return await embed_chunks_stage(session, paper_id=UUID(paper_id), embedder=embedder)

    return await _run_stage(
        ctx, stage_name="embed_chunks", job_id=job_id, paper_id=paper_id, runner=runner
    )
