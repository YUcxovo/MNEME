"""Focused tests for durable metadata ingestion and PDF fan-out."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from mneme.core.config import Settings
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.services.arxiv.ingestion import (
    ArxivIngestionResult,
    ArxivIngestionSummary,
    ArxivObservedRevision,
)
from mneme.tasks import document_runtime, metadata_jobs

PAPER_ID = UUID("00000000-0000-0000-0000-000000000111")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000222")
FETCH_JOB_ID = UUID("00000000-0000-0000-0000-000000000333")
RUN_DATE = date(2026, 7, 21)
NOW = datetime(2026, 7, 21, tzinfo=UTC)

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        self.rollbacks += 1

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None


class FakeDatabase:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def session_factory(self) -> FakeSession:
        return self.session


class FakeQueue:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> object:
        self.calls.append((function, args, kwargs))
        if self.fail:
            raise ConnectionError("redis unavailable")
        return SimpleNamespace()


class FakeJobRepository:
    def __init__(self, jobs: list[PipelineJob] | None = None) -> None:
        self.jobs = {job.id: job for job in jobs or []}
        self.released: list[UUID] = []

    async def get(self, job_id: UUID) -> PipelineJob | None:
        return self.jobs.get(job_id)

    async def get_or_create(self, **values: Any) -> tuple[PipelineJob, bool]:
        for job in self.jobs.values():
            if job.idempotency_key == values["idempotency_key"]:
                return job, False
        job = PipelineJob(
            id=uuid4(),
            idempotency_key=values["idempotency_key"],
            stage=values["stage"],
            paper_id=values["paper_id"],
            paper_version_id=values["paper_version_id"],
            pipeline_version="v1",
            status=JobStatus.QUEUED,
            attempt_count=0,
        )
        self.jobs[job.id] = job
        return job, True

    async def claim_failed_for_retry(self, job_id: UUID) -> bool:
        job = self.jobs[job_id]
        if job.status is not JobStatus.FAILED:
            return False
        job.status = JobStatus.QUEUED
        job.dispatched_at = None
        return True

    async def claim_for_dispatch(self, job_id: UUID, *, lease_seconds: int = 300) -> int | None:
        del lease_seconds
        job = self.jobs[job_id]
        if job.status is not JobStatus.QUEUED or job.dispatched_at is not None:
            return None
        job.dispatched_at = NOW
        return job.attempt_count + 1

    async def release_dispatch(self, job_id: UUID) -> None:
        self.jobs[job_id].dispatched_at = None
        self.released.append(job_id)

    async def mark_running(self, job_id: UUID) -> None:
        self.jobs[job_id].status = JobStatus.RUNNING

    async def mark_succeeded(self, job_id: UUID) -> None:
        self.jobs[job_id].status = JobStatus.SUCCEEDED

    async def mark_failed(self, job_id: UUID, *, error_code: str, message: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error_code = error_code
        job.last_error = message


def _fetch_job() -> PipelineJob:
    return PipelineJob(
        id=FETCH_JOB_ID,
        idempotency_key=metadata_jobs.metadata_idempotency_key(category="cs.AI", run_date=RUN_DATE),
        stage=PipelineStage.FETCH_METADATA,
        paper_id=None,
        paper_version_id=None,
        pipeline_version="v1",
        status=JobStatus.QUEUED,
        attempt_count=0,
    )


def _install_fakes(monkeypatch: pytest.MonkeyPatch, repository: FakeJobRepository) -> None:
    class FakeClient:
        def __init__(self, _: Settings) -> None:
            pass

        async def __aenter__(self) -> "FakeClient":
            return self

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    class FakeService:
        def __init__(self, client: object, session: object) -> None:
            del client, session

        async def ingest_category_detailed(
            self, category: str, *, max_results: int
        ) -> ArxivIngestionResult:
            assert (category, max_results) == ("cs.AI", 20)
            return ArxivIngestionResult(
                summary=ArxivIngestionSummary(1, 1, 1),
                revisions=(
                    ArxivObservedRevision(
                        paper_id=PAPER_ID,
                        paper_version_id=VERSION_ID,
                        arxiv_id="2607.00001",
                        version_number=2,
                        version_created=True,
                    ),
                ),
            )

    monkeypatch.setattr(metadata_jobs, "PipelineJobRepository", lambda _: repository)
    monkeypatch.setattr(document_runtime, "PipelineJobRepository", lambda _: repository)
    monkeypatch.setattr(metadata_jobs, "ArxivClient", FakeClient)
    monkeypatch.setattr(metadata_jobs, "ArxivIngestionService", FakeService)


def _run(
    monkeypatch: pytest.MonkeyPatch,
    queue: FakeQueue,
    repository: FakeJobRepository | None = None,
) -> tuple[str, FakeJobRepository]:
    repository = repository or FakeJobRepository([_fetch_job()])
    _install_fakes(monkeypatch, repository)
    outcome = asyncio.run(
        metadata_jobs.fetch_metadata(
            {
                "database": FakeDatabase(FakeSession()),
                "redis": queue,
                "settings": Settings(_env_file=None),
            },
            "cs.AI",
            RUN_DATE.isoformat(),
            20,
            job_id=str(FETCH_JOB_ID),
        )
    )
    return outcome, repository


def test_metadata_job_fans_out_exact_revision_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    queue = FakeQueue()
    outcome, repository = _run(monkeypatch, queue)

    assert outcome == "ok"
    assert repository.jobs[FETCH_JOB_ID].status is JobStatus.SUCCEEDED
    children = [job for job in repository.jobs.values() if job.stage is PipelineStage.DOWNLOAD_PDF]
    assert len(children) == 1
    child = children[0]
    assert (child.paper_id, child.paper_version_id) == (PAPER_ID, VERSION_ID)
    function, args, kwargs = queue.calls[0]
    assert function == "download_pdf"
    assert args == (str(PAPER_ID), str(VERSION_ID))
    assert kwargs == {
        "job_id": str(child.id),
        "_job_id": f"pipeline:{child.id}:attempt:1",
    }


def test_dispatch_failure_releases_child_and_fails_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeJobRepository([_fetch_job()])
    with pytest.raises(metadata_jobs.MetadataStageError, match="could not be dispatched"):
        _run(monkeypatch, FakeQueue(fail=True), repository)

    parent = repository.jobs[FETCH_JOB_ID]
    child = next(job for job in repository.jobs.values() if job.stage is PipelineStage.DOWNLOAD_PDF)
    assert parent.status is JobStatus.FAILED
    assert parent.error_code == "metadata_dispatch_failed"
    assert repository.released == [child.id]
    assert child.dispatched_at is None
