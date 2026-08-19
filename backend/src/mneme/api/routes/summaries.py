"""Authenticated AI summary endpoint (Milestone 2: cached or async)."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import (
    TaskQueue,
    get_artifact_repository,
    get_pipeline_job_repository,
    get_task_queue,
)
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.jobs import Job
from mneme.api.schemas.summaries import Summary
from mneme.db.dependencies import get_session
from mneme.models.job import JobStatus, PipelineStage
from mneme.models.paper import ProcessingStatus
from mneme.repositories.artifacts import ArtifactRepository
from mneme.repositories.job_identity import (
    download_idempotency_key,
    parse_idempotency_key,
    summarize_idempotency_key,
)
from mneme.repositories.jobs import PipelineJobRepository, arq_attempt_id
from mneme.repositories.paper_catalog import PaperCatalogRepository
from mneme.services.documents import PARSER_VERSION

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/papers", tags=["ai"])


@router.get(
    "/{paper_id}/summary",
    response_model=Summary,
    response_model_exclude_none=True,
    operation_id="getPaperSummary",
    responses={
        status.HTTP_200_OK: {"model": Summary},
        status.HTTP_202_ACCEPTED: {"model": Job},
        "default": {"model": ErrorResponse},
    },
)
async def get_paper_summary(
    paper_id: UUID,
    _principal: Annotated[Principal, Depends(require_principal)],
    catalog: Annotated[PaperCatalogRepository, Depends(get_paper_catalog_repository)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    jobs: Annotated[PipelineJobRepository, Depends(get_pipeline_job_repository)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Summary | JSONResponse:
    """Return the stored summary, or accept async generation (202 + Job).

    The first request for an unsummarized paper resumes the exact revision at
    its earliest missing download, parse, or summarize stage. Concurrent and
    repeated requests reuse the durable job, and a failed job is requeued so a
    client retry can recover.
    """
    paper = await catalog.get_paper(paper_id)
    if paper is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )

    version = await artifacts.get_latest_version(paper_id)
    if version is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            "paper_not_ready",
            "The requested paper has no observed revision.",
        )

    stored = await artifacts.get_summary_for_version(version.id)
    if stored is not None:
        return Summary.from_stored(stored)

    if version.parsed_checksum is not None and version.parser_version is not None:
        stage = PipelineStage.SUMMARIZE_PAPER
        idempotency_key = summarize_idempotency_key(
            paper_id=paper_id,
            paper_version_id=version.id,
            parsed_checksum=version.parsed_checksum,
            parser_version=version.parser_version,
        )
    elif version.source_checksum is not None:
        stage = PipelineStage.PARSE_PDF
        idempotency_key = parse_idempotency_key(
            paper_id=paper_id,
            paper_version_id=version.id,
            source_checksum=version.source_checksum,
            parser_version=PARSER_VERSION,
        )
    else:
        stage = PipelineStage.DOWNLOAD_PDF
        idempotency_key = download_idempotency_key(
            paper_id=paper_id,
            paper_version_id=version.id,
            arxiv_id=paper.arxiv_id,
            version_number=version.version_number,
        )

    job, created = await jobs.get_or_create(
        idempotency_key=idempotency_key,
        stage=stage,
        paper_id=paper_id,
        paper_version_id=version.id,
    )
    if not created and job.status is JobStatus.FAILED:
        await jobs.claim_failed_for_retry(job.id)
        job = await jobs.get(job.id) or job
    if paper.processing_status is ProcessingStatus.METADATA_ONLY:
        paper.processing_status = ProcessingStatus.QUEUED
    await session.commit()

    attempt = await jobs.claim_for_dispatch(job.id)
    await session.commit()
    if attempt is not None:
        try:
            await queue.enqueue_job(
                stage.value,
                str(paper_id),
                str(version.id),
                job_id=str(job.id),
                _job_id=arq_attempt_id(job.id, attempt),
            )
        except Exception as error:
            await jobs.release_dispatch(job.id)
            await session.commit()
            logger.warning(
                "summary_pipeline_enqueue_failed",
                paper_id=str(paper_id),
                paper_version_id=str(version.id),
                stage=stage.value,
            )
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "queue_unavailable",
                "Paper preparation is temporarily unavailable. Try again.",
            ) from error
        logger.info(
            "summary_pipeline_enqueued",
            paper_id=str(paper_id),
            paper_version_id=str(version.id),
            stage=stage.value,
            job_id=str(job.id),
        )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=Job.from_model(job).model_dump(mode="json"),
    )
