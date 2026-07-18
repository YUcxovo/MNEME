"""Authenticated AI summary endpoint (Milestone 2: cached or async)."""

from typing import Annotated
from uuid import UUID

import structlog
from fastapi import APIRouter, Depends, Response, status
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
from mneme.repositories.artifacts import ArtifactRepository
from mneme.repositories.jobs import PipelineJobRepository, summarize_idempotency_key
from mneme.repositories.paper_catalog import PaperCatalogRepository

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/papers", tags=["ai"])


@router.get(
    "/{paper_id}/summary",
    response_model=Summary | Job,
    operation_id="getPaperSummary",
    responses={
        status.HTTP_200_OK: {"model": Summary},
        status.HTTP_202_ACCEPTED: {"model": Job},
        "default": {"model": ErrorResponse},
    },
)
async def get_paper_summary(
    paper_id: UUID,
    response: Response,
    _principal: Annotated[Principal, Depends(require_principal)],
    catalog: Annotated[PaperCatalogRepository, Depends(get_paper_catalog_repository)],
    artifacts: Annotated[ArtifactRepository, Depends(get_artifact_repository)],
    jobs: Annotated[PipelineJobRepository, Depends(get_pipeline_job_repository)],
    queue: Annotated[TaskQueue, Depends(get_task_queue)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Summary | Job:
    """Return the stored summary, or accept async generation (202 + Job).

    The first request for an unsummarized paper creates one durable pipeline
    job and enqueues the summarize stage; concurrent and repeated requests
    reuse that job until it succeeds. A failed job is requeued so a client
    retry can recover.
    """
    paper = await catalog.get_paper(paper_id)
    if paper is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )

    stored = await artifacts.get_latest_summary(paper_id)
    if stored is not None:
        return Summary.from_stored(stored)

    job, created = await jobs.get_or_create(
        idempotency_key=summarize_idempotency_key(paper_id),
        stage=PipelineStage.SUMMARIZE_PAPER,
        paper_id=paper_id,
    )
    if not created and job.status is JobStatus.FAILED:
        job = await jobs.requeue(job)
        created = True
    await session.commit()

    if created:
        await queue.enqueue_job(
            "summarize_paper",
            str(paper_id),
            job_id=str(job.id),
            _job_id=job.idempotency_key,
        )
        logger.info("summary_generation_enqueued", paper_id=str(paper_id), job_id=str(job.id))

    response.status_code = status.HTTP_202_ACCEPTED
    return Job.from_model(job)
