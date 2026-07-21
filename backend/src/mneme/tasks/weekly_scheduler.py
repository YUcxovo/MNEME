"""Durable scheduling primitives for weekly Research Briefings."""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.job import JobStatus, PipelineStage
from mneme.repositories.job_identity import weekly_digest_idempotency_key
from mneme.repositories.jobs import PipelineJobRepository, arq_attempt_id
from mneme.services.recommendation import GENERATOR_VERSION
from mneme.tasks.daily_scheduler import JobQueue


class WeeklyScheduleError(RuntimeError):
    """The durable weekly briefing job could not be dispatched."""

    def __init__(self, job_id: UUID) -> None:
        self.job_id = job_id
        super().__init__("The weekly Research Briefing job could not be dispatched.")


@dataclass(frozen=True, slots=True)
class WeeklyScheduleSummary:
    """Machine-readable outcome for one idempotent weekly schedule attempt."""

    user_id: UUID
    week_start: date
    job_id: UUID
    job_created: bool
    job_requeued: bool
    job_dispatched: bool
    job_unchanged: bool


def validate_week_start(value: date) -> date:
    """Require the canonical UTC Monday boundary."""
    if value.weekday() != 0:
        raise ValueError("Weekly briefing periods must start on Monday.")
    return value


async def schedule_weekly(
    session: AsyncSession,
    queue: JobQueue,
    *,
    user_id: UUID,
    week_start: date,
) -> WeeklyScheduleSummary:
    """Create or recover the user/week job and acquire its dispatch lease."""
    validate_week_start(week_start)
    jobs = PipelineJobRepository(session)
    job, created = await jobs.get_or_create(
        idempotency_key=weekly_digest_idempotency_key(
            user_id=user_id,
            week_start=week_start,
            generator_version=GENERATOR_VERSION,
        ),
        stage=PipelineStage.ASSEMBLE_DIGEST,
        paper_id=None,
        paper_version_id=None,
    )

    requeued = False
    dispatchable = created or job.status is JobStatus.QUEUED
    if not created and job.status is JobStatus.FAILED:
        requeued = await jobs.claim_failed_for_retry(job.id)
        dispatchable = requeued
    await session.commit()

    dispatched = False
    if dispatchable:
        attempt = await jobs.claim_for_dispatch(job.id)
        await session.commit()
        if attempt is not None:
            try:
                await queue.enqueue_job(
                    "assemble_digest",
                    str(user_id),
                    week_start.isoformat(),
                    job_id=str(job.id),
                    _job_id=arq_attempt_id(job.id, attempt),
                )
                dispatched = True
            except Exception as error:
                await jobs.release_dispatch(job.id)
                await session.commit()
                raise WeeklyScheduleError(job.id) from error

    return WeeklyScheduleSummary(
        user_id=user_id,
        week_start=week_start,
        job_id=job.id,
        job_created=created,
        job_requeued=requeued,
        job_dispatched=dispatched,
        job_unchanged=not dispatched,
    )
