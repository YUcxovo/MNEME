"""Tests for lease-based recovery of revision pipeline dispatches."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.tasks import dispatch_recovery

PAPER_ID = UUID("00000000-0000-0000-0000-000000000111")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000222")
NOW = datetime(2026, 7, 21, tzinfo=UTC)

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


class FakeSession:
    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1

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
    def __init__(self, *, fail_first: bool = False) -> None:
        self.fail_first = fail_first
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> object:
        self.calls.append((function, args, kwargs))
        if self.fail_first and len(self.calls) == 1:
            raise ConnectionError("redis unavailable")
        return SimpleNamespace()


class FakeRepository:
    def __init__(self, jobs: list[PipelineJob], *, block: set[UUID] | None = None) -> None:
        self.jobs = {job.id: job for job in jobs}
        self.block = block or set()
        self.list_call: tuple[int, int, bool] | None = None
        self.released: list[UUID] = []

    async def list_dispatchable(
        self, *, lease_seconds: int, limit: int, revision_only: bool
    ) -> list[UUID]:
        self.list_call = (lease_seconds, limit, revision_only)
        return list(self.jobs)

    async def get(self, job_id: UUID) -> PipelineJob | None:
        return self.jobs.get(job_id)

    async def claim_for_dispatch(self, job_id: UUID, *, lease_seconds: int) -> int | None:
        job = self.jobs[job_id]
        if job_id in self.block:
            return None
        job.dispatched_at = NOW
        return job.attempt_count + 1

    async def release_dispatch(self, job_id: UUID) -> None:
        self.jobs[job_id].dispatched_at = None
        self.released.append(job_id)


def _revision_job(stage: PipelineStage, *, attempt_count: int = 0) -> PipelineJob:
    return PipelineJob(
        id=uuid4(),
        idempotency_key=f"v1:{stage.value}:{'a' * 64}",
        stage=stage,
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        pipeline_version="v1",
        status=JobStatus.QUEUED,
        attempt_count=attempt_count,
    )


def _collection_job() -> PipelineJob:
    return PipelineJob(
        id=uuid4(),
        idempotency_key=f"v1:assemble_digest:{'b' * 64}",
        stage=PipelineStage.ASSEMBLE_DIGEST,
        paper_id=None,
        paper_version_id=None,
        pipeline_version="v1",
        status=JobStatus.QUEUED,
        attempt_count=0,
    )


def _run(
    monkeypatch: pytest.MonkeyPatch,
    repository: FakeRepository,
    queue: FakeQueue,
) -> int:
    session = FakeSession()
    monkeypatch.setattr(dispatch_recovery, "PipelineJobRepository", lambda _: repository)
    return asyncio.run(
        dispatch_recovery.recover_revision_dispatches(
            {"database": FakeDatabase(session), "redis": queue},
            lease_seconds=60,
            limit=25,
        )
    )


def test_recovery_dispatches_exact_revision_with_stable_attempt_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _revision_job(PipelineStage.PARSE_PDF, attempt_count=2)
    repository = FakeRepository([job, _collection_job()])
    queue = FakeQueue()

    dispatched = _run(monkeypatch, repository, queue)

    assert dispatched == 1
    assert repository.list_call == (60, 25, True)
    function, args, kwargs = queue.calls[0]
    assert function == "parse_pdf"
    assert args == (str(PAPER_ID), str(VERSION_ID))
    assert kwargs == {
        "job_id": str(job.id),
        "_job_id": f"pipeline:{job.id}:attempt:3",
    }


def test_recovery_skips_a_job_claimed_by_another_dispatcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _revision_job(PipelineStage.DOWNLOAD_PDF)
    repository = FakeRepository([job], block={job.id})
    queue = FakeQueue()

    assert _run(monkeypatch, repository, queue) == 0
    assert queue.calls == []


def test_recovery_releases_failed_enqueue_and_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _revision_job(PipelineStage.CHUNK_PAPER)
    second = _revision_job(PipelineStage.EMBED_CHUNKS)
    repository = FakeRepository([first, second])

    dispatched = _run(monkeypatch, repository, FakeQueue(fail_first=True))

    assert dispatched == 1
    assert repository.released == [first.id]
    assert first.dispatched_at is None
    assert second.dispatched_at == NOW


def test_recovery_without_worker_queue_is_a_noop() -> None:
    outcome = asyncio.run(dispatch_recovery.recover_revision_dispatches({"database": object()}))

    assert outcome == 0
