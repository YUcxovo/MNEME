"""Recover revision jobs stranded between database commit and Redis enqueue."""

from typing import Any, Final

import structlog

from mneme.models.job import PipelineStage
from mneme.repositories.jobs import PipelineJobRepository, arq_attempt_id

logger = structlog.get_logger(__name__)

_REVISION_FUNCTIONS: Final = frozenset(
    {
        PipelineStage.DOWNLOAD_PDF,
        PipelineStage.PARSE_PDF,
        PipelineStage.SUMMARIZE_PAPER,
        PipelineStage.CHUNK_PAPER,
        PipelineStage.EMBED_CHUNKS,
    }
)


async def recover_revision_dispatches(
    ctx: dict[str, Any], *, lease_seconds: int = 300, limit: int = 100
) -> int:
    """Lease and enqueue queued revision jobs, including stale dispatches."""
    queue = ctx.get("redis")
    if queue is None:
        logger.warning("dispatch_recovery_queue_unavailable")
        return 0

    dispatched = 0
    database = ctx["database"]
    async with database.session_factory() as session:
        jobs = PipelineJobRepository(session)
        candidates = await jobs.list_dispatchable(
            lease_seconds=lease_seconds,
            limit=limit,
            revision_only=True,
        )
        for job_id in candidates:
            job = await jobs.get(job_id)
            if (
                job is None
                or job.stage not in _REVISION_FUNCTIONS
                or job.paper_id is None
                or job.paper_version_id is None
            ):
                continue
            attempt = await jobs.claim_for_dispatch(job.id, lease_seconds=lease_seconds)
            await session.commit()
            if attempt is None:
                continue
            try:
                await queue.enqueue_job(
                    job.stage.value,
                    str(job.paper_id),
                    str(job.paper_version_id),
                    job_id=str(job.id),
                    _job_id=arq_attempt_id(job.id, attempt),
                )
                dispatched += 1
            except Exception:
                await jobs.release_dispatch(job.id)
                await session.commit()
                logger.warning(
                    "dispatch_recovery_enqueue_failed",
                    job_id=str(job.id),
                    stage=job.stage.value,
                )

    logger.info("dispatch_recovery_completed", candidates=len(candidates), dispatched=dispatched)
    return dispatched
