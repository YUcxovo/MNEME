"""Durable ARQ worker for weekly Research Briefing assembly."""

from datetime import UTC, date, datetime, time
from typing import Any, Final
from uuid import UUID

import structlog

from mneme.core.config import Settings
from mneme.models.digest import DigestType
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.user import User
from mneme.repositories.digests import DigestRepository
from mneme.repositories.job_identity import (
    PIPELINE_VERSION,
    weekly_digest_idempotency_key,
)
from mneme.repositories.jobs import PipelineJobRepository
from mneme.services.recommendation import GENERATOR_VERSION, RecommendedDigestService

logger = structlog.get_logger(__name__)

_FAILURE_CODE: Final = "digest_assembly_failed"
_FAILURE_MESSAGE: Final = "The weekly Research Briefing could not be assembled."


def _valid_job(job: PipelineJob, *, expected_key: str) -> bool:
    return (
        job.idempotency_key == expected_key
        and job.stage is PipelineStage.ASSEMBLE_DIGEST
        and job.paper_id is None
        and job.paper_version_id is None
        and job.pipeline_version == PIPELINE_VERSION
    )


async def _fail_job(
    jobs: PipelineJobRepository,
    job_id: UUID,
    *,
    error_code: str,
    message: str,
) -> None:
    await jobs.mark_failed(job_id, error_code=error_code, message=message)


async def assemble_digest(
    ctx: dict[str, Any],
    user_id: str,
    week_start: str,
    *,
    job_id: str,
) -> str:
    """Persist one exact user/week briefing and finalize its durable job."""
    try:
        resolved_user_id = UUID(user_id)
        resolved_week_start = date.fromisoformat(week_start)
        resolved_job_id = UUID(job_id)
        expected_key = weekly_digest_idempotency_key(
            user_id=resolved_user_id,
            week_start=resolved_week_start,
            generator_version=GENERATOR_VERSION,
        )
    except (TypeError, ValueError):
        return "invalid_digest_job"

    settings: Settings = ctx["settings"]
    database = ctx["database"]
    async with database.session_factory() as session:
        jobs = PipelineJobRepository(session)
        job = await jobs.get(resolved_job_id)
        if job is None:
            return "digest_job_not_found"
        if not _valid_job(job, expected_key=expected_key):
            return "digest_job_identity_mismatch"
        if job.status is JobStatus.SUCCEEDED:
            return "already_succeeded"
        if job.status is JobStatus.RUNNING:
            return "already_running"

        user = await session.get(User, resolved_user_id)
        if user is None:
            await _fail_job(
                jobs,
                resolved_job_id,
                error_code="digest_user_not_found",
                message="The configured briefing user does not exist.",
            )
            await session.commit()
            return "digest_user_not_found"

        await jobs.mark_running(resolved_job_id)
        await session.commit()
        try:
            service = RecommendedDigestService(
                DigestRepository(session),
                candidate_days=settings.ai_recommendation_candidate_days,
                max_entries=settings.ai_recommendation_max_entries,
            )
            cutoff = datetime.combine(resolved_week_start, time.min, tzinfo=UTC)
            bundle = await service.generate(
                resolved_user_id,
                digest_type=DigestType.WEEKLY,
                as_of=cutoff,
            )
            await jobs.mark_succeeded(resolved_job_id)
            await session.commit()
        except BaseException:
            await session.rollback()
            await _fail_job(
                jobs,
                resolved_job_id,
                error_code=_FAILURE_CODE,
                message=_FAILURE_MESSAGE,
            )
            await session.commit()
            logger.exception(
                "weekly_digest_assembly_failed",
                user_id=user_id,
                week_start=week_start,
            )
            raise

        logger.info(
            "weekly_digest_assembled",
            user_id=user_id,
            week_start=week_start,
            digest_id=str(bundle.digest.id),
            entries=len(bundle.entries),
        )
        return "ok"
