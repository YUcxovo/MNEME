"""Durable pipeline-job state used by AI endpoints for 202 responses.

The queue infrastructure itself is owned by Ruiyu; this repository only
covers the narrow surface AI endpoints need: get-or-create one queued job
per idempotency key and record stage transitions from the worker.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.models.job import JobStatus, PipelineJob, PipelineStage

PIPELINE_VERSION = "v1"


def summarize_idempotency_key(paper_id: UUID) -> str:
    """Stable key: at most one endpoint-triggered summarize job per paper."""
    return f"summarize_paper:{paper_id}"


class PipelineJobRepository:
    """Create and update pipeline jobs through one request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: UUID) -> PipelineJob | None:
        """Return one job by id."""
        return await self._session.scalar(select(PipelineJob).where(PipelineJob.id == job_id))

    async def get_or_create(
        self, *, idempotency_key: str, stage: PipelineStage, paper_id: UUID | None
    ) -> tuple[PipelineJob, bool]:
        """Return the existing job for a key, or a new queued one.

        The boolean is True when this call created the job (the caller is
        then responsible for enqueuing the corresponding ARQ task).
        """
        existing = await self._session.scalar(
            select(PipelineJob).where(PipelineJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing, False
        job = PipelineJob(
            paper_id=paper_id,
            idempotency_key=idempotency_key,
            stage=stage,
            status=JobStatus.QUEUED,
            pipeline_version=PIPELINE_VERSION,
        )
        self._session.add(job)
        await self._session.flush()
        return job, True

    async def requeue(self, job: PipelineJob) -> PipelineJob:
        """Reset a failed job so its stage can be enqueued again."""
        job.status = JobStatus.QUEUED
        job.error_code = None
        job.last_error = None
        job.started_at = None
        job.finished_at = None
        await self._session.flush()
        return job

    async def mark_running(self, job_id: UUID) -> None:
        """Record that a worker picked the job up."""
        job = await self.get(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.attempt_count += 1
        job.started_at = utc_now()
        await self._session.flush()

    async def mark_succeeded(self, job_id: UUID) -> None:
        """Record a successful run."""
        job = await self.get(job_id)
        if job is None:
            return
        job.status = JobStatus.SUCCEEDED
        job.error_code = None
        job.last_error = None
        job.finished_at = utc_now()
        await self._session.flush()

    async def mark_failed(self, job_id: UUID, *, error_code: str, message: str) -> None:
        """Record a failed run with its stable error code."""
        job = await self.get(job_id)
        if job is None:
            return
        job.status = JobStatus.FAILED
        job.error_code = error_code
        job.last_error = message[:2000]
        job.finished_at = utc_now()
        await self._session.flush()
