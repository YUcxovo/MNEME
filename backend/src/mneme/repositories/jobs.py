"""Canonical identities and persistence for durable pipeline jobs."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.repositories.job_identity import (
    PIPELINE_VERSION,
    PipelineJobIdentityConflictError,
    validate_requested_identity,
    validate_stored_identity,
)


def arq_attempt_id(job_id: UUID, attempt_number: int) -> str:
    """Return one Redis identity that remains stable until a worker starts."""
    if attempt_number < 1:
        raise ValueError("ARQ attempt number must be positive.")
    return f"pipeline:{job_id}:attempt:{attempt_number}"


class PipelineJobRepository:
    """Create and update pipeline jobs through one request session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, job_id: UUID) -> PipelineJob | None:
        """Return one job by id."""
        return await self._session.scalar(select(PipelineJob).where(PipelineJob.id == job_id))

    async def get_or_create(
        self,
        *,
        idempotency_key: str,
        stage: PipelineStage,
        paper_id: UUID | None,
        paper_version_id: UUID | None,
        pipeline_version: str = PIPELINE_VERSION,
    ) -> tuple[PipelineJob, bool]:
        """Atomically return the job for one exact durable identity.

        PostgreSQL arbitrates concurrent creators through the unique key. The
        boolean is true only for the transaction that inserted the row; that
        caller alone is responsible for enqueuing the corresponding ARQ task.
        """
        validate_requested_identity(
            idempotency_key=idempotency_key,
            stage=stage,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            pipeline_version=pipeline_version,
        )

        now = utc_now()
        job_id = uuid4()
        statement = (
            postgresql_insert(PipelineJob)
            .values(
                id=job_id,
                paper_id=paper_id,
                paper_version_id=paper_version_id,
                idempotency_key=idempotency_key,
                stage=stage,
                status=JobStatus.QUEUED,
                attempt_count=0,
                pipeline_version=pipeline_version,
                created_at=now,
                updated_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_pipeline_jobs_idempotency_key")
            .returning(PipelineJob.id)
        )
        inserted_id = (await self._session.execute(statement)).scalar_one_or_none()
        if inserted_id is not None:
            inserted = await self._session.get(PipelineJob, inserted_id)
            if inserted is None:  # pragma: no cover - guarded by the current transaction
                raise PipelineJobIdentityConflictError
            return inserted, True

        existing = await self._session.scalar(
            select(PipelineJob).where(PipelineJob.idempotency_key == idempotency_key)
        )
        if existing is None:  # pragma: no cover - only possible after an external concurrent delete
            raise PipelineJobIdentityConflictError
        validate_stored_identity(
            existing,
            stage=stage,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            pipeline_version=pipeline_version,
        )
        return existing, False

    async def claim_failed_for_retry(self, job_id: UUID) -> bool:
        """Atomically let one caller move a failed job back to the queue."""
        now = utc_now()
        statement = (
            update(PipelineJob)
            .where(PipelineJob.id == job_id, PipelineJob.status == JobStatus.FAILED)
            .values(
                status=JobStatus.QUEUED,
                error_code=None,
                last_error=None,
                dispatched_at=None,
                started_at=None,
                finished_at=None,
                updated_at=now,
            )
            .returning(PipelineJob.id)
        )
        return (await self._session.execute(statement)).scalar_one_or_none() is not None

    async def requeue(self, job: PipelineJob) -> PipelineJob:
        """Compatibility wrapper around the atomic failed-job retry claim."""
        await self.claim_failed_for_retry(job.id)
        refreshed = await self._session.get(PipelineJob, job.id, populate_existing=True)
        return refreshed or job

    async def claim_for_dispatch(self, job_id: UUID, *, lease_seconds: int = 300) -> int | None:
        """Claim one queued job for ARQ and return its stable attempt number.

        A stale lease can be reclaimed after a process dies between the
        database commit and Redis enqueue. The returned attempt stays stable
        until a worker actually starts and increments ``attempt_count``.
        """
        if lease_seconds < 1:
            raise ValueError("Dispatch lease must be positive.")
        now = utc_now()
        stale_before = now - timedelta(seconds=lease_seconds)
        statement = (
            update(PipelineJob)
            .where(
                PipelineJob.id == job_id,
                PipelineJob.status == JobStatus.QUEUED,
                or_(
                    PipelineJob.dispatched_at.is_(None),
                    PipelineJob.dispatched_at < stale_before,
                ),
            )
            .values(dispatched_at=now, updated_at=now)
            .returning(PipelineJob.attempt_count)
        )
        attempt_count = (await self._session.execute(statement)).scalar_one_or_none()
        return attempt_count + 1 if attempt_count is not None else None

    async def release_dispatch(self, job_id: UUID) -> None:
        """Release a queue lease after Redis rejects an enqueue attempt."""
        await self._session.execute(
            update(PipelineJob)
            .where(PipelineJob.id == job_id, PipelineJob.status == JobStatus.QUEUED)
            .values(dispatched_at=None, updated_at=utc_now())
        )

    async def list_dispatchable(
        self,
        *,
        lease_seconds: int = 300,
        limit: int = 100,
        revision_only: bool = False,
    ) -> list[UUID]:
        """List queued jobs whose dispatch lease is absent or stale."""
        if lease_seconds < 1 or limit < 1:
            raise ValueError("Dispatch lease and limit must be positive.")
        stale_before = utc_now() - timedelta(seconds=lease_seconds)
        statement = select(PipelineJob.id).where(
            PipelineJob.status == JobStatus.QUEUED,
            or_(
                PipelineJob.dispatched_at.is_(None),
                PipelineJob.dispatched_at < stale_before,
            ),
        )
        if revision_only:
            statement = statement.where(PipelineJob.paper_version_id.is_not(None))
        statement = statement.order_by(PipelineJob.created_at, PipelineJob.id).limit(limit)
        return list((await self._session.scalars(statement)).all())

    async def list_failed_latest_revision_jobs(
        self, paper_ids: tuple[UUID, ...]
    ) -> list[PipelineJob]:
        """Return failed jobs bound to each paper's latest observed revision."""
        if not paper_ids:
            return []
        latest_version_number = (
            select(func.max(PaperVersion.version_number))
            .where(PaperVersion.paper_id == PipelineJob.paper_id)
            .correlate(PipelineJob)
            .scalar_subquery()
        )
        statement = (
            select(PipelineJob)
            .join(PaperVersion, PaperVersion.id == PipelineJob.paper_version_id)
            .join(Paper, Paper.id == PipelineJob.paper_id)
            .where(
                PipelineJob.paper_id.in_(paper_ids),
                PipelineJob.status == JobStatus.FAILED,
                PipelineJob.pipeline_version == PIPELINE_VERSION,
                PaperVersion.version_number == latest_version_number,
                Paper.processing_status != ProcessingStatus.READY,
            )
            .order_by(PipelineJob.created_at, PipelineJob.id)
        )
        return list((await self._session.scalars(statement)).all())

    async def mark_running(self, job_id: UUID) -> None:
        """Record that a worker picked the job up."""
        job = await self.get(job_id)
        if job is None:
            return
        job.status = JobStatus.RUNNING
        job.attempt_count += 1
        job.error_code = None
        job.last_error = None
        job.started_at = utc_now()
        job.finished_at = None
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
