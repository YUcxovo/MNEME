"""Recovery and idempotency tests for the daily metadata scheduler."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.tasks import daily_scheduler, metadata_jobs

RUN_DATE = date(2026, 7, 21)
NOW = datetime(2026, 7, 21, tzinfo=UTC)

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


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

    async def mark_failed(self, job_id: UUID, *, error_code: str, message: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error_code = error_code
        job.last_error = message


def _job(category: str, status: JobStatus = JobStatus.QUEUED) -> PipelineJob:
    return PipelineJob(
        id=uuid4(),
        idempotency_key=metadata_jobs.metadata_idempotency_key(
            category=category, run_date=RUN_DATE
        ),
        stage=PipelineStage.FETCH_METADATA,
        paper_id=None,
        paper_version_id=None,
        pipeline_version="v1",
        status=status,
        attempt_count=0,
    )


def _schedule(
    monkeypatch: pytest.MonkeyPatch,
    repository: FakeJobRepository,
    queue: FakeQueue,
    categories: tuple[str, ...] = ("cs.AI",),
) -> daily_scheduler.DailyScheduleSummary:
    monkeypatch.setattr(daily_scheduler, "PipelineJobRepository", lambda _: repository)
    return asyncio.run(
        daily_scheduler.schedule_daily(
            cast(AsyncSession, FakeSession()),
            queue,
            run_date=RUN_DATE,
            categories=categories,
            max_results=20,
        )
    )


def test_repeat_schedule_reuses_live_dispatch_leases(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = FakeJobRepository()
    queue = FakeQueue()

    first = _schedule(monkeypatch, repository, queue, ("cs.AI", "cs.LG"))
    second = _schedule(monkeypatch, repository, queue, ("cs.AI", "cs.LG"))

    assert first.jobs_created == first.jobs_dispatched == 2
    assert second.jobs_created == second.jobs_dispatched == 0
    assert second.jobs_unchanged == 2
    assert len(repository.jobs) == len(queue.calls) == 2
    for function, args, kwargs in queue.calls:
        assert function == "fetch_metadata"
        assert args[1:] == (RUN_DATE.isoformat(), 20)
        assert kwargs["_job_id"] == f"pipeline:{kwargs['job_id']}:attempt:1"


def test_undispatched_queued_job_is_recovered(monkeypatch: pytest.MonkeyPatch) -> None:
    existing = _job("cs.AI")
    repository = FakeJobRepository([existing])
    queue = FakeQueue()

    summary = _schedule(monkeypatch, repository, queue)

    assert summary.jobs_created == 0
    assert summary.jobs_dispatched == 1
    assert queue.calls[0][2]["job_id"] == str(existing.id)


def test_failed_job_is_atomically_requeued(monkeypatch: pytest.MonkeyPatch) -> None:
    failed = _job("cs.AI", JobStatus.FAILED)
    repository = FakeJobRepository([failed])

    summary = _schedule(monkeypatch, repository, FakeQueue())

    assert summary.jobs_requeued == summary.jobs_dispatched == 1
    assert failed.status is JobStatus.QUEUED
    assert failed.dispatched_at == NOW


def test_enqueue_failure_releases_lease_and_records_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeJobRepository()

    with pytest.raises(daily_scheduler.DailyScheduleError) as captured:
        _schedule(monkeypatch, repository, FakeQueue(fail=True))

    assert captured.value.failed_categories == ("cs.AI",)
    job = next(iter(repository.jobs.values()))
    assert job.status is JobStatus.FAILED
    assert job.error_code == "metadata_enqueue_failed"
    assert repository.released == [job.id]
    assert job.dispatched_at is None
