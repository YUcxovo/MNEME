"""Durable state and transaction tests for weekly digest assembly jobs."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest

from mneme.core.config import Settings
from mneme.models.digest import DigestType
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.user import User
from mneme.repositories.job_identity import weekly_digest_idempotency_key
from mneme.services.recommendation import GENERATOR_VERSION
from mneme.tasks import digest_jobs

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
JOB_ID = UUID("00000000-0000-0000-0000-000000000222")
WEEK_START = date(2026, 7, 20)

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


class FakeSession:
    def __init__(self, *, user_exists: bool = True) -> None:
        self.user_exists = user_exists
        self.commits = 0
        self.rollbacks = 0

    async def get(self, model: type[Any], identity: UUID) -> object | None:
        if model is User and identity == USER_ID and self.user_exists:
            return User(id=USER_ID, display_name="Demo")
        return None

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


class FakeJobRepository:
    def __init__(self, job: PipelineJob) -> None:
        self.job = job

    async def get(self, job_id: UUID) -> PipelineJob | None:
        return self.job if job_id == self.job.id else None

    async def mark_running(self, job_id: UUID) -> None:
        assert job_id == self.job.id
        self.job.status = JobStatus.RUNNING
        self.job.attempt_count += 1

    async def mark_succeeded(self, job_id: UUID) -> None:
        assert job_id == self.job.id
        self.job.status = JobStatus.SUCCEEDED
        self.job.error_code = None

    async def mark_failed(self, job_id: UUID, *, error_code: str, message: str) -> None:
        assert job_id == self.job.id
        self.job.status = JobStatus.FAILED
        self.job.error_code = error_code
        self.job.last_error = message


class FakeDigestService:
    calls: ClassVar[list[tuple[UUID, DigestType, datetime]]] = []
    should_fail: ClassVar[bool] = False
    entry_count: ClassVar[int] = 1

    def __init__(self, repository: object, *, candidate_days: int, max_entries: int) -> None:
        del repository
        assert candidate_days > 0
        assert max_entries > 0

    async def generate(
        self, user_id: UUID, *, digest_type: DigestType, as_of: datetime
    ) -> SimpleNamespace:
        self.calls.append((user_id, digest_type, as_of))
        if self.should_fail:
            raise RuntimeError("recommendation failed")
        return SimpleNamespace(
            digest=SimpleNamespace(id=uuid4()),
            entries=[object() for _ in range(self.entry_count)],
        )


def _job(status: JobStatus = JobStatus.QUEUED) -> PipelineJob:
    return PipelineJob(
        id=JOB_ID,
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
        attempt_count=0,
    )


def _install(
    monkeypatch: pytest.MonkeyPatch,
    repository: FakeJobRepository,
) -> None:
    FakeDigestService.calls.clear()
    FakeDigestService.should_fail = False
    FakeDigestService.entry_count = 1
    monkeypatch.setattr(digest_jobs, "PipelineJobRepository", lambda _: repository)
    monkeypatch.setattr(digest_jobs, "DigestRepository", lambda _: object())
    monkeypatch.setattr(digest_jobs, "RecommendedDigestService", FakeDigestService)


def _run(session: FakeSession) -> str:
    return asyncio.run(
        digest_jobs.assemble_digest(
            {
                "database": FakeDatabase(session),
                "settings": Settings(_env_file=None),
            },
            str(USER_ID),
            WEEK_START.isoformat(),
            job_id=str(JOB_ID),
        )
    )


def test_weekly_worker_persists_period_and_succeeds_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job()
    repository = FakeJobRepository(job)
    session = FakeSession()
    _install(monkeypatch, repository)

    outcome = _run(session)

    assert outcome == "ok"
    assert job.status is JobStatus.SUCCEEDED
    assert job.attempt_count == 1
    assert session.commits == 2
    assert FakeDigestService.calls == [
        (
            USER_ID,
            DigestType.WEEKLY,
            datetime(2026, 7, 20, tzinfo=UTC),
        )
    ]


def test_empty_weekly_digest_is_successful(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _job()
    _install(monkeypatch, FakeJobRepository(job))
    FakeDigestService.entry_count = 0

    assert _run(FakeSession()) == "ok"
    assert job.status is JobStatus.SUCCEEDED


def test_successful_replay_does_not_generate_again(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _job(JobStatus.SUCCEEDED)
    _install(monkeypatch, FakeJobRepository(job))

    assert _run(FakeSession()) == "already_succeeded"
    assert FakeDigestService.calls == []


def test_missing_user_records_terminal_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _job()
    _install(monkeypatch, FakeJobRepository(job))

    assert _run(FakeSession(user_exists=False)) == "digest_user_not_found"
    assert job.status is JobStatus.FAILED
    assert job.error_code == "digest_user_not_found"


def test_generation_failure_rolls_back_output_and_records_safe_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job()
    session = FakeSession()
    _install(monkeypatch, FakeJobRepository(job))
    FakeDigestService.should_fail = True

    with pytest.raises(RuntimeError, match="recommendation failed"):
        _run(session)

    assert session.rollbacks == 1
    assert job.status is JobStatus.FAILED
    assert job.error_code == "digest_assembly_failed"
    assert "recommendation" not in (job.last_error or "")


def test_mismatched_job_identity_is_not_mutated(monkeypatch: pytest.MonkeyPatch) -> None:
    job = _job()
    job.idempotency_key = weekly_digest_idempotency_key(
        user_id=uuid4(),
        week_start=WEEK_START,
        generator_version=GENERATOR_VERSION,
    )
    _install(monkeypatch, FakeJobRepository(job))

    assert _run(FakeSession()) == "digest_job_identity_mismatch"
    assert job.status is JobStatus.QUEUED


def test_previous_generator_job_cannot_mask_current_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job = _job()
    job.idempotency_key = weekly_digest_idempotency_key(
        user_id=USER_ID,
        week_start=WEEK_START,
        generator_version="recommender-v1",
    )
    _install(monkeypatch, FakeJobRepository(job))

    assert GENERATOR_VERSION == "recommender-v2"
    assert _run(FakeSession()) == "digest_job_identity_mismatch"
    assert job.status is JobStatus.QUEUED
