"""Durable execution primitives shared by revision-scoped AI jobs."""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.budget import BudgetExceededError
from mneme.ai.pipeline import PaperNotReadyError
from mneme.ai.types import LLMProviderError, ProviderNotConfiguredError
from mneme.core.timeouts import AI_STAGE_EXECUTION_TIMEOUT_SECONDS
from mneme.models.job import JobStatus, PipelineStage
from mneme.repositories.job_identity import PIPELINE_VERSION
from mneme.repositories.jobs import PipelineJobRepository
from mneme.services.documents import DocumentStorage, ParsedDocument

logger = structlog.get_logger(__name__)

StageRunner = Callable[[AsyncSession], Awaitable[object]]


class ParsedDocumentUnavailableError(RuntimeError):
    """The immutable parser sidecar required by an AI stage is unavailable."""


class AIStageTimeoutError(TimeoutError):
    """The complete AI stage exhausted its bounded execution budget."""


async def load_parsed_document(
    ctx: dict[str, Any], *, paper_id: UUID, paper_version_id: UUID
) -> ParsedDocument:
    """Load and validate one parser sidecar without carrying it through Redis."""
    storage: DocumentStorage = ctx["document_storage"]
    try:
        document = await asyncio.to_thread(storage.read_parsed_document, paper_id, paper_version_id)
    except (OSError, ValidationError) as error:
        raise ParsedDocumentUnavailableError(
            "The parsed document artifact is unavailable or invalid."
        ) from error
    if document.paper_id != paper_id or document.paper_version_id != paper_version_id:
        raise ParsedDocumentUnavailableError(
            "The parsed document does not match the requested paper revision."
        )
    return document


async def run_ai_stage(
    ctx: dict[str, Any],
    *,
    stage: PipelineStage,
    job_id: str | None,
    paper_id: str,
    paper_version_id: str,
    runner: StageRunner,
) -> str:
    """Run one exact-revision AI stage with durable error bookkeeping."""
    try:
        resolved_paper_id = UUID(paper_id)
        resolved_version_id = UUID(paper_version_id)
        resolved_job_id = UUID(job_id) if job_id is not None else None
    except ValueError:
        return "invalid_job_identity"

    database = ctx["database"]
    async with database.session_factory() as session:
        jobs = PipelineJobRepository(session)
        if resolved_job_id is not None:
            job = await jobs.get(resolved_job_id)
            if job is None:
                return "pipeline_job_not_found"
            if (
                job.stage != stage
                or job.paper_id != resolved_paper_id
                or job.paper_version_id != resolved_version_id
                or job.pipeline_version != PIPELINE_VERSION
            ):
                return "pipeline_job_identity_mismatch"
            if job.status is JobStatus.SUCCEEDED:
                return "already_succeeded"
            if job.status is JobStatus.RUNNING:
                return "already_running"
            await jobs.mark_running(resolved_job_id)
            await session.commit()

        try:
            async with asyncio.timeout(AI_STAGE_EXECUTION_TIMEOUT_SECONDS):
                outcome = await runner(session)
            await session.commit()
        except BudgetExceededError as error:
            result = ("ai_budget_exhausted", "budget_exhausted", error, False)
        except ProviderNotConfiguredError as error:
            result = ("ai_provider_unconfigured", "provider_unconfigured", error, False)
        except LLMProviderError as error:
            result = ("ai_provider_error", "provider_error", error, error.retryable)
        except PaperNotReadyError as error:
            result = ("paper_not_ready", "paper_not_ready", error, False)
        except ParsedDocumentUnavailableError as error:
            result = ("parsed_document_unavailable", "parsed_document_unavailable", error, False)
        except TimeoutError:
            result = (
                "ai_stage_timeout",
                "ai_stage_timeout",
                AIStageTimeoutError("The AI stage exceeded its complete execution budget."),
                True,
            )
        except BaseException:
            await session.rollback()
            if resolved_job_id is not None:
                await jobs.mark_failed(
                    resolved_job_id,
                    error_code="ai_stage_error",
                    message="The AI pipeline stage failed unexpectedly.",
                )
                await session.commit()
            logger.exception(
                "ai_stage_crashed",
                stage=stage.value,
                paper_id=paper_id,
                paper_version_id=paper_version_id,
            )
            raise
        else:
            if resolved_job_id is not None:
                await jobs.mark_succeeded(resolved_job_id)
                await session.commit()
            logger.info(
                "ai_stage_completed",
                stage=stage.value,
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                outcome=outcome,
            )
            return "ok"

        error_code, response, error, retryable = result
        await session.rollback()
        if resolved_job_id is not None:
            await jobs.mark_failed(resolved_job_id, error_code=error_code, message=str(error))
            await session.commit()
        logger.warning(
            "ai_stage_failed",
            stage=stage.value,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            error_code=error_code,
        )
        if retryable:
            raise error
        return response
