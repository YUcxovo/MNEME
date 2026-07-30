"""Bounded read-only aggregation for platform operations."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.digest import Digest, DigestType
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ParseQuality, ProcessingStatus

PLATFORM_OPERATIONS_SCHEMA_VERSION = "platform-operations-v1"
MAX_WINDOW_HOURS = 30 * 24
MAX_DISPATCH_LEASE_SECONDS = 24 * 60 * 60
MAX_FAILED_LIMIT = 100


def _enum_counts(values: type[ProcessingStatus] | type[DigestType]) -> dict[str, int]:
    return {item.value: 0 for item in values}


def _stage_status_counts() -> dict[str, dict[str, dict[str, int]]]:
    return {
        stage.value: {status.value: {"count": 0, "attempts": 0} for status in JobStatus}
        for stage in PipelineStage
    }


class PlatformOperationsRepository:
    """Build a safe operational report from durable PostgreSQL state."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def snapshot(
        self,
        *,
        now: datetime,
        window_hours: int,
        dispatch_lease_seconds: int,
        failed_limit: int,
    ) -> dict[str, object]:
        """Return one bounded report without loading raw operational errors."""
        self._validate_bounds(
            now=now,
            window_hours=window_hours,
            dispatch_lease_seconds=dispatch_lease_seconds,
            failed_limit=failed_limit,
        )
        end = now.astimezone(UTC)
        start = end - timedelta(hours=window_hours)
        stale_before = end - timedelta(seconds=dispatch_lease_seconds)

        job_activity = _stage_status_counts()
        created_jobs = 0
        dispatch_attempts = 0
        job_rows = (
            await self._session.execute(
                select(
                    PipelineJob.stage,
                    PipelineJob.status,
                    func.count(PipelineJob.id),
                    func.coalesce(func.sum(PipelineJob.attempt_count), 0),
                )
                .where(PipelineJob.created_at >= start, PipelineJob.created_at < end)
                .group_by(PipelineJob.stage, PipelineJob.status)
            )
        ).all()
        for stage, status, count, attempts in job_rows:
            count_value = int(count)
            attempt_value = int(attempts)
            job_activity[stage.value][status.value] = {
                "count": count_value,
                "attempts": attempt_value,
            }
            created_jobs += count_value
            dispatch_attempts += attempt_value

        active_row = (
            await self._session.execute(
                select(
                    func.count(PipelineJob.id)
                    .filter(PipelineJob.status == JobStatus.QUEUED)
                    .label("queued"),
                    func.count(PipelineJob.id)
                    .filter(PipelineJob.status == JobStatus.RUNNING)
                    .label("running"),
                    func.count(PipelineJob.id)
                    .filter(
                        PipelineJob.status == JobStatus.QUEUED,
                        PipelineJob.dispatched_at.is_(None),
                    )
                    .label("undispatched_queued"),
                    func.count(PipelineJob.id)
                    .filter(
                        PipelineJob.status == JobStatus.QUEUED,
                        PipelineJob.dispatched_at.is_not(None),
                        PipelineJob.dispatched_at < stale_before,
                    )
                    .label("stale_dispatched_queued"),
                ).where(PipelineJob.status.in_((JobStatus.QUEUED, JobStatus.RUNNING)))
            )
        ).one()
        queued, running, undispatched_queued, stale_dispatched_queued = map(int, active_row)

        failed_window = (
            PipelineJob.status == JobStatus.FAILED,
            PipelineJob.finished_at.is_not(None),
            PipelineJob.finished_at >= start,
            PipelineJob.finished_at < end,
        )
        failed_result = await self._session.execute(
            select(func.count(PipelineJob.id)).where(*failed_window)
        )
        failed_jobs = int(failed_result.scalar_one())
        recent_failures: list[dict[str, object]] = []
        if failed_limit:
            failure_rows = (
                await self._session.execute(
                    select(
                        PipelineJob.id,
                        PipelineJob.stage,
                        PipelineJob.error_code,
                        PipelineJob.attempt_count,
                        PipelineJob.created_at,
                        PipelineJob.started_at,
                        PipelineJob.finished_at,
                    )
                    .where(*failed_window)
                    .order_by(PipelineJob.finished_at.desc(), PipelineJob.id.desc())
                    .limit(failed_limit)
                )
            ).all()
            recent_failures = [
                {
                    "id": job_id,
                    "stage": stage.value,
                    "error_code": error_code,
                    "attempt_count": int(attempt_count),
                    "created_at": created_at,
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
                for (
                    job_id,
                    stage,
                    error_code,
                    attempt_count,
                    created_at,
                    started_at,
                    finished_at,
                ) in failure_rows
            ]

        processing_counts = _enum_counts(ProcessingStatus)
        total_papers = 0
        created_papers = 0
        paper_rows = (
            await self._session.execute(
                select(
                    Paper.processing_status,
                    func.count(Paper.id),
                    func.count(Paper.id).filter(Paper.created_at >= start, Paper.created_at < end),
                ).group_by(Paper.processing_status)
            )
        ).all()
        for status, count, created in paper_rows:
            count_value = int(count)
            processing_counts[status.value] = count_value
            total_papers += count_value
            created_papers += int(created)

        latest_versions = (
            select(PaperVersion.paper_id, PaperVersion.parse_quality)
            .distinct(PaperVersion.paper_id)
            .order_by(PaperVersion.paper_id, PaperVersion.version_number.desc())
            .subquery()
        )
        parse_quality_counts = {item.value: 0 for item in ParseQuality}
        parse_quality_counts["not_parsed"] = 0
        quality_rows = (
            await self._session.execute(
                select(latest_versions.c.parse_quality, func.count(Paper.id))
                .select_from(Paper)
                .outerjoin(latest_versions, latest_versions.c.paper_id == Paper.id)
                .group_by(latest_versions.c.parse_quality)
            )
        ).all()
        for quality, count in quality_rows:
            key = "not_parsed" if quality is None else quality.value
            parse_quality_counts[key] = int(count)

        digest_counts = _enum_counts(DigestType)
        generated_digests = 0
        digest_rows = (
            await self._session.execute(
                select(Digest.digest_type, func.count(Digest.id))
                .where(Digest.generated_at >= start, Digest.generated_at < end)
                .group_by(Digest.digest_type)
            )
        ).all()
        for digest_type, count in digest_rows:
            count_value = int(count)
            digest_counts[digest_type.value] = count_value
            generated_digests += count_value

        return {
            "schema_version": PLATFORM_OPERATIONS_SCHEMA_VERSION,
            "generated_at": end,
            "window": {"start": start, "end": end, "hours": window_hours},
            "jobs": {
                "created": created_jobs,
                "dispatch_attempts": dispatch_attempts,
                "by_stage_status": job_activity,
                "queued": queued,
                "running": running,
                "undispatched_queued": undispatched_queued,
                "stale_dispatched_queued": stale_dispatched_queued,
                "failed": failed_jobs,
                "recent_failures": recent_failures,
            },
            "papers": {
                "total": total_papers,
                "created": created_papers,
                "by_processing_status": processing_counts,
                "latest_parse_quality": parse_quality_counts,
            },
            "digests": {
                "generated": generated_digests,
                "by_type": digest_counts,
            },
        }

    @staticmethod
    def _validate_bounds(
        *,
        now: datetime,
        window_hours: int,
        dispatch_lease_seconds: int,
        failed_limit: int,
    ) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Platform operations time must be timezone-aware.")
        if not 1 <= window_hours <= MAX_WINDOW_HOURS:
            raise ValueError(f"Window hours must be between 1 and {MAX_WINDOW_HOURS}.")
        if not 1 <= dispatch_lease_seconds <= MAX_DISPATCH_LEASE_SECONDS:
            raise ValueError("Dispatch lease seconds must be between 1 and 86400.")
        if not 0 <= failed_limit <= MAX_FAILED_LIMIT:
            raise ValueError(f"Failed limit must be between 0 and {MAX_FAILED_LIMIT}.")
