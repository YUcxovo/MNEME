"""Durable daily arXiv metadata ingestion and document-pipeline fan-out."""

from __future__ import annotations

from datetime import date
from typing import Any, Final
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.core.config import Settings
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.repositories.job_identity import (
    PIPELINE_VERSION,
    build_job_idempotency_key,
    download_idempotency_key,
)
from mneme.repositories.jobs import PipelineJobRepository
from mneme.services.arxiv.client import ArxivClient, ArxivClientError
from mneme.services.arxiv.ingestion import ArxivIngestionService, ArxivObservedRevision
from mneme.services.arxiv.parser import ArxivParseError
from mneme.tasks.document_runtime import (
    DocumentStageError,
    PendingEnqueue,
    dispatch_pending,
    ensure_child_job,
)

logger = structlog.get_logger(__name__)

_UNEXPECTED_ERROR_CODE: Final = "metadata_stage_error"
_UNEXPECTED_ERROR_MESSAGE: Final = "The metadata pipeline stage failed unexpectedly."


class MetadataStageError(RuntimeError):
    """Safe metadata-stage failure with a stable persisted error code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(message)


def metadata_idempotency_key(*, category: str, run_date: date) -> str:
    """Return the one durable metadata identity for a category and UTC date."""
    if not category:
        raise ValueError("The arXiv category must not be empty.")
    return build_job_idempotency_key(
        stage=PipelineStage.FETCH_METADATA,
        scope={"category": category, "run_date": run_date.isoformat()},
        inputs={},
    )


def _valid_parent(job: PipelineJob, *, expected_key: str) -> bool:
    return (
        job.idempotency_key == expected_key
        and job.stage is PipelineStage.FETCH_METADATA
        and job.paper_id is None
        and job.paper_version_id is None
        and job.pipeline_version == PIPELINE_VERSION
    )


async def _ensure_download_jobs(
    session: AsyncSession,
    revisions: tuple[ArxivObservedRevision, ...],
) -> list[PendingEnqueue]:
    pending: list[PendingEnqueue] = []
    for revision in revisions:
        child = await ensure_child_job(
            session,
            idempotency_key=download_idempotency_key(
                paper_id=revision.paper_id,
                paper_version_id=revision.paper_version_id,
                arxiv_id=revision.arxiv_id,
                version_number=revision.version_number,
            ),
            stage=PipelineStage.DOWNLOAD_PDF,
            paper_id=revision.paper_id,
            paper_version_id=revision.paper_version_id,
            function="download_pdf",
        )
        if child is not None:
            pending.append(child)
    return pending


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


async def fetch_metadata(
    ctx: dict[str, Any],
    category: str,
    run_date: str,
    max_results: int,
    *,
    job_id: str,
) -> str:
    """Ingest one category page and fan out exact revision IDs to PDF jobs."""
    try:
        resolved_job_id = UUID(job_id)
        resolved_date = date.fromisoformat(run_date)
        expected_key = metadata_idempotency_key(category=category, run_date=resolved_date)
    except (TypeError, ValueError):
        return "invalid_metadata_job"

    settings: Settings = ctx["settings"]
    database = ctx["database"]
    async with database.session_factory() as session:
        jobs = PipelineJobRepository(session)
        job = await jobs.get(resolved_job_id)
        if job is None:
            return "metadata_job_not_found"
        if not _valid_parent(job, expected_key=expected_key):
            return "metadata_job_identity_mismatch"
        if job.status is JobStatus.SUCCEEDED:
            return "already_succeeded"
        if job.status is JobStatus.RUNNING:
            return "already_running"
        if not 1 <= max_results <= settings.arxiv_max_results:
            await jobs.mark_failed(
                resolved_job_id,
                error_code="metadata_request_invalid",
                message="The configured metadata request is invalid.",
            )
            await session.commit()
            return "invalid_metadata_request"

        await jobs.mark_running(resolved_job_id)
        await session.commit()
        try:
            if ctx.get("redis") is None:
                raise MetadataStageError(
                    "metadata_queue_unavailable",
                    "The metadata pipeline queue is unavailable.",
                    retryable=True,
                )
            async with ArxivClient(settings) as client:
                result = await ArxivIngestionService(client, session).ingest_category_detailed(
                    category,
                    max_results=max_results,
                )
            pending = await _ensure_download_jobs(session, result.revisions)
            await session.commit()
            dispatched = await dispatch_pending(ctx, session, pending)
        except ValueError:
            await _record_failure(
                session,
                jobs,
                resolved_job_id,
                code="metadata_request_invalid",
                message="The configured metadata request is invalid.",
            )
            logger.warning("metadata_request_invalid", category=category, run_date=run_date)
            return "metadata_request_invalid"
        except (ArxivClientError, ArxivParseError) as error:
            safe_error = MetadataStageError(
                "metadata_ingestion_failed",
                "The arXiv metadata feed could not be ingested.",
                retryable=True,
            )
            await _record_failure(
                session,
                jobs,
                resolved_job_id,
                code=safe_error.code,
                message=str(safe_error),
            )
            logger.warning(
                "metadata_ingestion_failed",
                category=category,
                run_date=run_date,
                error_type=type(error).__name__,
            )
            raise safe_error from error
        except MetadataStageError as error:
            await _record_failure(
                session,
                jobs,
                resolved_job_id,
                code=error.code,
                message=str(error),
            )
            logger.warning(
                "metadata_dispatch_failed",
                category=category,
                run_date=run_date,
                error_code=error.code,
            )
            if error.retryable:
                raise
            return error.code
        except DocumentStageError as error:
            safe_error = MetadataStageError(
                "metadata_dispatch_failed",
                "A durable PDF download job could not be dispatched.",
                retryable=error.retryable,
            )
            await _record_failure(
                session,
                jobs,
                resolved_job_id,
                code=safe_error.code,
                message=str(safe_error),
            )
            logger.warning(
                "metadata_dispatch_failed",
                category=category,
                run_date=run_date,
                error_code=safe_error.code,
            )
            if safe_error.retryable:
                raise safe_error from error
            return safe_error.code
        except BaseException:
            await _record_failure(
                session,
                jobs,
                resolved_job_id,
                code=_UNEXPECTED_ERROR_CODE,
                message=_UNEXPECTED_ERROR_MESSAGE,
            )
            logger.exception("metadata_stage_crashed", category=category, run_date=run_date)
            raise

        await jobs.mark_succeeded(resolved_job_id)
        await session.commit()
        logger.info(
            "metadata_stage_completed",
            category=category,
            run_date=run_date,
            records_received=result.summary.records_received,
            downloads_dispatched=dispatched,
        )
        return "ok"
