"""Durable execution and dispatch primitives for document pipeline stages."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.repositories.job_identity import PIPELINE_VERSION
from mneme.repositories.jobs import PipelineJobRepository, arq_attempt_id
from mneme.services.documents import PdfDownloadError, PdfParseError

logger = structlog.get_logger(__name__)

_UNEXPECTED_ERROR_CODE: Final = "document_stage_error"
_UNEXPECTED_ERROR_MESSAGE: Final = "The document pipeline stage failed unexpectedly."


class DocumentStageError(RuntimeError):
    """Safe stage failure with a stable persisted error code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PendingEnqueue:
    """A durable child job that may be dispatched after commit."""

    function: str
    paper_id: UUID
    paper_version_id: UUID
    job_id: UUID


StageRunner = Callable[[AsyncSession, UUID, UUID], Awaitable[list[PendingEnqueue]]]


def _validate_job_identity(
    job: PipelineJob,
    *,
    stage: PipelineStage,
    paper_id: UUID,
    paper_version_id: UUID,
) -> None:
    if (
        job.stage != stage
        or job.paper_id != paper_id
        or job.paper_version_id != paper_version_id
        or job.pipeline_version != PIPELINE_VERSION
    ):
        raise DocumentStageError(
            "pipeline_job_identity_mismatch",
            "The durable job does not match the requested document stage.",
        )


async def _record_failure(
    session: AsyncSession,
    jobs: PipelineJobRepository,
    job_id: UUID,
    *,
    code: str,
    message: str,
) -> None:
    await session.rollback()
    await jobs.mark_failed(job_id, error_code=code, message=message)
    await session.commit()


async def dispatch_pending(
    ctx: dict[str, Any], session: AsyncSession, pending: list[PendingEnqueue]
) -> int:
    """Claim and enqueue children with recoverable database leases."""
    queue = ctx.get("redis")
    if queue is None:
        raise DocumentStageError(
            "queue_unavailable", "The pipeline queue is unavailable.", retryable=True
        )
    jobs = PipelineJobRepository(session)
    dispatched = 0
    for child in pending:
        attempt = await jobs.claim_for_dispatch(child.job_id)
        await session.commit()
        if attempt is None:
            continue
        try:
            await queue.enqueue_job(
                child.function,
                str(child.paper_id),
                str(child.paper_version_id),
                job_id=str(child.job_id),
                _job_id=arq_attempt_id(child.job_id, attempt),
            )
            dispatched += 1
        except Exception as error:
            await jobs.release_dispatch(child.job_id)
            await session.commit()
            raise DocumentStageError(
                "queue_enqueue_failed",
                "A durable child job could not be dispatched.",
                retryable=True,
            ) from error
    return dispatched


async def run_document_stage(
    ctx: dict[str, Any],
    *,
    stage: PipelineStage,
    job_id: str,
    paper_id: str,
    paper_version_id: str,
    runner: StageRunner,
) -> str:
    """Validate identity, transact output, dispatch children, and finalize state."""
    try:
        resolved_job_id = UUID(job_id)
        resolved_paper_id = UUID(paper_id)
        resolved_version_id = UUID(paper_version_id)
    except ValueError:
        return "invalid_job_identity"

    database = ctx["database"]
    async with database.session_factory() as session:
        jobs = PipelineJobRepository(session)
        job = await jobs.get(resolved_job_id)
        if job is None:
            return "pipeline_job_not_found"
        try:
            _validate_job_identity(
                job,
                stage=stage,
                paper_id=resolved_paper_id,
                paper_version_id=resolved_version_id,
            )
        except DocumentStageError as error:
            return error.code
        if job.status is JobStatus.SUCCEEDED:
            return "already_succeeded"
        if job.status is JobStatus.RUNNING:
            return "already_running"

        await jobs.mark_running(resolved_job_id)
        await session.commit()
        try:
            pending = await runner(session, resolved_paper_id, resolved_version_id)
            await session.commit()
            await dispatch_pending(ctx, session, pending)
        except (DocumentStageError, PdfDownloadError, PdfParseError) as error:
            await _record_failure(
                session, jobs, resolved_job_id, code=error.code, message=str(error)
            )
            logger.warning(
                "document_stage_failed",
                stage=stage.value,
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                error_code=error.code,
            )
            if getattr(error, "retryable", False):
                raise
            return error.code
        except BaseException:
            await _record_failure(
                session,
                jobs,
                resolved_job_id,
                code=_UNEXPECTED_ERROR_CODE,
                message=_UNEXPECTED_ERROR_MESSAGE,
            )
            logger.exception(
                "document_stage_crashed",
                stage=stage.value,
                paper_id=paper_id,
                paper_version_id=paper_version_id,
            )
            raise

        await jobs.mark_succeeded(resolved_job_id)
        await session.commit()
        logger.info(
            "document_stage_completed",
            stage=stage.value,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
        )
        return "ok"


async def ensure_child_job(
    session: AsyncSession,
    *,
    stage: PipelineStage,
    function: str,
    paper_id: UUID,
    paper_version_id: UUID,
    idempotency_key: str,
) -> PendingEnqueue | None:
    """Create or retry a durable child, leaving dispatch to the caller."""
    repository = PipelineJobRepository(session)
    job, _ = await repository.get_or_create(
        idempotency_key=idempotency_key,
        stage=stage,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
    )
    if job.status in {JobStatus.SUCCEEDED, JobStatus.RUNNING}:
        return None
    if job.status is JobStatus.FAILED and not await repository.claim_failed_for_retry(job.id):
        return None
    return PendingEnqueue(function, paper_id, paper_version_id, job.id)
