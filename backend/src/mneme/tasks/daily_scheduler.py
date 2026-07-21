"""Durable scheduling primitives for daily arXiv metadata ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mneme.core.config import Settings
from mneme.models.job import JobStatus, PipelineStage
from mneme.repositories.jobs import PipelineJobRepository, arq_attempt_id
from mneme.services.arxiv.client import CATEGORY_PATTERN
from mneme.tasks.metadata_jobs import metadata_idempotency_key


class JobQueue(Protocol):
    """The subset of ARQ used by cron-facing schedulers."""

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> object:
        """Enqueue one named task."""
        ...


class DailyScheduleError(RuntimeError):
    """One or more durable metadata jobs could not be dispatched."""

    def __init__(self, failed_categories: tuple[str, ...]) -> None:
        self.failed_categories = failed_categories
        super().__init__("One or more daily metadata jobs could not be dispatched.")


@dataclass(frozen=True, slots=True)
class PendingMetadata:
    """A queued metadata job that should attempt to acquire a dispatch lease."""

    category: str
    job_id: UUID


@dataclass(frozen=True, slots=True)
class DailyScheduleSummary:
    """Machine-readable outcome for one cron invocation."""

    run_date: date
    categories: tuple[str, ...]
    jobs_created: int
    jobs_requeued: int
    jobs_unchanged: int
    jobs_dispatched: int


def validate_request(
    settings: Settings,
    *,
    categories: tuple[str, ...],
    max_results: int,
) -> tuple[str, ...]:
    """Normalize and validate one daily scheduling request before I/O."""
    values = (category.strip() for category in categories if category.strip())
    normalized = tuple(dict.fromkeys(values))
    if not normalized:
        raise ValueError("At least one arXiv category must be configured.")
    if any(CATEGORY_PATTERN.fullmatch(category) is None for category in normalized):
        raise ValueError("One or more configured arXiv categories are invalid.")
    if not 1 <= max_results <= settings.arxiv_max_results:
        raise ValueError("Daily max results exceeds the configured arXiv page bound.")
    return normalized


async def schedule_daily(
    session: AsyncSession,
    queue: JobQueue,
    *,
    run_date: date,
    categories: tuple[str, ...],
    max_results: int,
) -> DailyScheduleSummary:
    """Create one durable category/date job and safely dispatch queued work."""
    jobs = PipelineJobRepository(session)
    pending: list[PendingMetadata] = []
    created_count = 0
    requeued_count = 0
    unchanged_count = 0

    for category in categories:
        job, created = await jobs.get_or_create(
            idempotency_key=metadata_idempotency_key(category=category, run_date=run_date),
            stage=PipelineStage.FETCH_METADATA,
            paper_id=None,
            paper_version_id=None,
        )
        if created:
            created_count += 1
            pending.append(PendingMetadata(category, job.id))
        elif job.status is JobStatus.FAILED:
            if await jobs.claim_failed_for_retry(job.id):
                requeued_count += 1
                pending.append(PendingMetadata(category, job.id))
            else:
                unchanged_count += 1
        elif job.status is JobStatus.QUEUED:
            pending.append(PendingMetadata(category, job.id))
        else:
            unchanged_count += 1
    await session.commit()

    dispatched = 0
    failed: list[str] = []
    for item in pending:
        attempt = await jobs.claim_for_dispatch(item.job_id)
        await session.commit()
        if attempt is None:
            unchanged_count += 1
            continue
        try:
            await queue.enqueue_job(
                "fetch_metadata",
                item.category,
                run_date.isoformat(),
                max_results,
                job_id=str(item.job_id),
                _job_id=arq_attempt_id(item.job_id, attempt),
            )
            dispatched += 1
        except Exception:
            await jobs.release_dispatch(item.job_id)
            await jobs.mark_failed(
                item.job_id,
                error_code="metadata_enqueue_failed",
                message="The daily metadata job could not be dispatched.",
            )
            await session.commit()
            failed.append(item.category)

    if failed:
        raise DailyScheduleError(tuple(failed))
    return DailyScheduleSummary(
        run_date=run_date,
        categories=categories,
        jobs_created=created_count,
        jobs_requeued=requeued_count,
        jobs_unchanged=unchanged_count,
        jobs_dispatched=dispatched,
    )
