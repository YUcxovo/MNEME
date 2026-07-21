"""Idempotency and recovery tests for weekly briefing scheduling."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.repositories.job_identity import weekly_digest_idempotency_key
from mneme.services.recommendation import GENERATOR_VERSION
from mneme.tasks import weekly_scheduler

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
WEEK_START = date(2026, 7, 20)
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
    def __init__(self, job: PipelineJob | None = None) -> None:
        self.job = job
        self.released: list[UUID] = []

    async def get_or_create(self, **values: Any) -> tuple[PipelineJob, bool]:
        if self.job is not None:
            return self.job, False
        self.job = PipelineJob(
            id=uuid4(),
            idempotency_key=values["idempotency_key"],
            stage=values["stage"],
            paper_id=values["paper_id"],
            paper_version_id=values["paper_version_id"],
            pipeline_version="v1",
            status=JobStatus.QUEUED,
            attempt_count=0,
        )
        return self.job, True

    async def claim_failed_for_retry(self, job_id: UUID) -> bool:
        assert self.job is not None and self.job.id == job_id
        if self.job.status is not JobStatus.FAILED:
            return False
        self.job.status = JobStatus.QUEUED
        self.job.dispatched_at = None
        return True

    async def claim_for_dispatch(self, job_id: UUID, *, lease_seconds: int = 300) -> int | None:
        del lease_seconds
        assert self.job is not None and self.job.id == job_id
        if self.job.status is not JobStatus.QUEUED or self.job.dispatched_at is not None:
            return None
        self.job.dispatched_at = NOW
        return self.job.attempt_count + 1

    async def release_dispatch(self, job_id: UUID) -> None:
        assert self.job is not None and self.job.id == job_id
        self.job.dispatched_at = None
        self.released.append(job_id)


def _job(status: JobStatus, *, attempt_count: int = 0) -> PipelineJob:
    return PipelineJob(
        id=uuid4(),
        idempotency_key=weekly_digest_idempotency_key(
            user_id=USER_ID,
            week_start=WEEK_START,
            generator_version=GENERATOR_VERSION,
        ),
        stage=PipelineStage.ASSEMBLE_DIGEST,
        paper_id=None,
        paper_version_id=None,
        pipeline_version="v1",
        status=status,
        attempt_count=attempt_count,
    )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    repository: FakeJobRepository,
    queue: FakeQueue,
) -> weekly_scheduler.WeeklyScheduleSummary:
    monkeypatch.setattr(weekly_scheduler, "PipelineJobRepository", lambda _: repository)
    return asyncio.run(
        weekly_scheduler.schedule_weekly(
            cast(AsyncSession, FakeSession()),
            queue,
            user_id=USER_ID,
            week_start=WEEK_START,
        )
    )


def test_new_week_dispatches_one_stable_job(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = FakeJobRepository()
    queue = FakeQueue()

    summary = _run(monkeypatch, repository, queue)

    assert summary.job_created is summary.job_dispatched is True
    assert summary.job_unchanged is False
    function, args, kwargs = queue.calls[0]
    assert function == "assemble_digest"
    assert args == (str(USER_ID), WEEK_START.isoformat())
    assert kwargs == {
        "job_id": str(summary.job_id),
        "_job_id": f"pipeline:{summary.job_id}:attempt:1",
    }


def test_same_week_reuses_live_dispatch_lease(monkeypatch: pytest.MonkeyPatch) -> None:
    repository = FakeJobRepository()
    queue = FakeQueue()

    first = _run(monkeypatch, repository, queue)
    second = _run(monkeypatch, repository, queue)

    assert first.job_id == second.job_id
    assert second.job_created is second.job_dispatched is False
    assert second.job_unchanged is True
    assert len(queue.calls) == 1


def test_failed_weekly_job_is_requeued(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _job(JobStatus.FAILED, attempt_count=2)
    summary = _run(monkeypatch, FakeJobRepository(job), FakeQueue())

    assert summary.job_requeued is summary.job_dispatched is True
    assert job.status is JobStatus.QUEUED
    assert job.dispatched_at == NOW


@pytest.mark.parametrize("status", [JobStatus.RUNNING, JobStatus.SUCCEEDED])
def test_inflight_or_finished_job_is_unchanged(
    monkeypatch: pytest.MonkeyPatch, status: JobStatus
) -> None:
    summary = _run(monkeypatch, FakeJobRepository(_job(status)), FakeQueue())

    assert summary.job_dispatched is False
    assert summary.job_unchanged is True


def test_queue_failure_releases_lease_for_next_daily_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repository = FakeJobRepository()

    with pytest.raises(weekly_scheduler.WeeklyScheduleError):
        _run(monkeypatch, repository, FakeQueue(fail=True))

    assert repository.job is not None
    assert repository.job.status is JobStatus.QUEUED
    assert repository.job.dispatched_at is None
    assert repository.released == [repository.job.id]


def test_non_monday_period_is_rejected() -> None:
    with pytest.raises(ValueError, match="Monday"):
        asyncio.run(
            weekly_scheduler.schedule_weekly(
                cast(AsyncSession, FakeSession()),
                FakeQueue(),
                user_id=USER_ID,
                week_start=date(2026, 7, 21),
            )
        )
