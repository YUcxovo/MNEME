"""Authenticated pipeline-job status endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from mneme.api.dependencies.ai import get_pipeline_job_repository
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.jobs import Job
from mneme.repositories.jobs import PipelineJobRepository

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    response_model=Job,
    operation_id="getJob",
    responses={"default": {"model": ErrorResponse}},
)
async def get_job(
    job_id: UUID,
    _principal: Annotated[Principal, Depends(require_principal)],
    jobs: Annotated[PipelineJobRepository, Depends(get_pipeline_job_repository)],
) -> Job:
    """Return the public state of one durable pipeline job."""
    job = await jobs.get(job_id)
    if job is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "job_not_found",
            "The requested pipeline job does not exist.",
        )
    return Job.from_model(job)
