"""Reference parsing and durable pipeline helpers for seed onboarding."""

from __future__ import annotations

import asyncio
import re
from typing import Final
from urllib.parse import urlparse
from uuid import UUID

from fastapi import status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.ai import TaskQueue
from mneme.api.errors import ApiError
from mneme.models.job import JobStatus, PipelineStage
from mneme.models.paper import Paper, ProcessingStatus
from mneme.repositories.job_identity import download_idempotency_key
from mneme.repositories.jobs import PipelineJobRepository, arq_attempt_id
from mneme.services.arxiv.ingestion import ArxivObservedRevision

_ARXIV_REFERENCE = re.compile(r"(?P<base>(?:\d{4}\.\d{4,5}|[A-Za-z0-9._-]+/\d{7}))(?:v[1-9]\d*)?$")
_ALLOWED_HOSTS: Final = frozenset({"arxiv.org", "www.arxiv.org", "export.arxiv.org"})
_POLL_INTERVAL_SECONDS: Final = 1.0
_INITIALIZATION_TIMEOUT_SECONDS: Final = 12 * 60


def normalize_arxiv_reference(value: str) -> str:
    """Return an unversioned arXiv ID from a supported URL or raw identifier."""
    candidate = value.strip()
    if "://" in candidate:
        parsed = urlparse(candidate)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in _ALLOWED_HOSTS:
            raise ValueError("The seed paper must use an arxiv.org URL.")
        path = parsed.path.strip("/")
        if path.startswith("abs/"):
            candidate = path.removeprefix("abs/")
        elif path.startswith("pdf/"):
            candidate = path.removeprefix("pdf/").removesuffix(".pdf")
        else:
            raise ValueError("Use an arXiv abstract or PDF URL.")
    candidate = candidate.removesuffix(".pdf")
    match = _ARXIV_REFERENCE.fullmatch(candidate)
    if match is None:
        raise ValueError("Enter a valid arXiv URL or identifier.")
    return match.group("base")


async def enqueue_seed_downloads(
    session: AsyncSession,
    queue: TaskQueue,
    revisions: tuple[ArxivObservedRevision, ...],
) -> tuple[UUID, ...]:
    """Create or resume the durable download pipeline for selected revisions."""
    jobs = PipelineJobRepository(session)
    dispatches: list[tuple[ArxivObservedRevision, UUID]] = []
    for revision in revisions:
        job, _created = await jobs.get_or_create(
            idempotency_key=download_idempotency_key(
                paper_id=revision.paper_id,
                paper_version_id=revision.paper_version_id,
                arxiv_id=revision.arxiv_id,
                version_number=revision.version_number,
            ),
            stage=PipelineStage.DOWNLOAD_PDF,
            paper_id=revision.paper_id,
            paper_version_id=revision.paper_version_id,
        )
        if job.status is JobStatus.FAILED:
            await jobs.claim_failed_for_retry(job.id)
        paper = await session.get(Paper, revision.paper_id)
        if paper is not None and paper.processing_status in {
            ProcessingStatus.METADATA_ONLY,
            ProcessingStatus.FAILED,
        }:
            paper.processing_status = ProcessingStatus.QUEUED
        dispatches.append((revision, job.id))
    await session.commit()

    for revision, job_id in dispatches:
        attempt = await jobs.claim_for_dispatch(job_id)
        await session.commit()
        if attempt is None:
            continue
        try:
            await queue.enqueue_job(
                PipelineStage.DOWNLOAD_PDF.value,
                str(revision.paper_id),
                str(revision.paper_version_id),
                job_id=str(job_id),
                _job_id=arq_attempt_id(job_id, attempt),
            )
        except Exception as error:
            await jobs.release_dispatch(job_id)
            await session.commit()
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "queue_unavailable",
                "The paper preparation queue is temporarily unavailable.",
            ) from error
    return tuple(revision.paper_id for revision in revisions)


async def wait_for_seed_papers(session: AsyncSession, paper_ids: tuple[UUID, ...]) -> None:
    """Block until every selected paper reaches a usable terminal state."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + _INITIALIZATION_TIMEOUT_SECONDS
    expected_ids = set(paper_ids)
    while True:
        rows = (
            await session.execute(
                select(Paper.id, Paper.processing_status).where(Paper.id.in_(expected_ids))
            )
        ).all()
        await session.rollback()
        statuses = {paper_id: processing_status for paper_id, processing_status in rows}
        if set(statuses) == expected_ids and all(
            item in {ProcessingStatus.READY, ProcessingStatus.PARTIAL} for item in statuses.values()
        ):
            return
        if any(item is ProcessingStatus.FAILED for item in statuses.values()):
            raise ApiError(
                status.HTTP_502_BAD_GATEWAY,
                "seed_initialization_failed",
                "The backend could not prepare the papers required for initialization.",
            )
        if loop.time() >= deadline:
            raise ApiError(
                status.HTTP_504_GATEWAY_TIMEOUT,
                "seed_initialization_timeout",
                "Preparing five related papers took too long. Try again to resume the work.",
            )
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
