"""Failure-contract tests for seed onboarding orchestration."""

import asyncio
from types import SimpleNamespace
from typing import ClassVar
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.api.dependencies.auth import Principal
from mneme.api.errors import ApiError
from mneme.api.routes import onboarding, onboarding_support
from mneme.api.schemas.onboarding import SeedInitializationRequest
from mneme.core.config import Settings
from mneme.models.job import JobStatus, PipelineStage
from mneme.models.paper import ProcessingStatus
from mneme.services.arxiv.ingestion import ArxivObservedRevision


class FailingQueue:
    """ARQ-compatible queue that rejects one dispatch."""

    async def enqueue_job(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("sensitive broker diagnostics")


class InternallyFailingArxivClient:
    """Client fake that raises an unrelated implementation ValueError."""

    def __init__(self, _settings: Settings) -> None:
        pass

    async def __aenter__(self) -> "InternallyFailingArxivClient":
        return self

    async def __aexit__(self, *_args: object) -> None:
        return None

    async def fetch_by_id(self, _arxiv_id: str) -> None:
        raise ValueError("sensitive internal state")


class FakeJobRepository:
    """Record durable dispatch recovery without using PostgreSQL."""

    released: ClassVar[list[object]] = []

    def __init__(self, _session: AsyncSession) -> None:
        self.job_id = uuid4()

    async def get_or_create(self, **_kwargs: object) -> tuple[SimpleNamespace, bool]:
        return SimpleNamespace(id=self.job_id, status=JobStatus.QUEUED), True

    async def claim_failed_for_retry(self, _job_id: object) -> bool:
        return False

    async def claim_for_dispatch(self, _job_id: object) -> int:
        return 1

    async def release_dispatch(self, job_id: object) -> None:
        self.released.append(job_id)


class FakeFailedJobRepository:
    """Expose one failed revision job for seed-resume tests."""

    released: ClassVar[list[object]] = []
    job_id = uuid4()
    paper_id = uuid4()
    paper_version_id = uuid4()

    def __init__(self, _session: AsyncSession) -> None:
        pass

    async def list_failed_latest_revision_jobs(
        self, paper_ids: tuple[object, ...]
    ) -> list[SimpleNamespace]:
        assert self.paper_id in paper_ids
        return [
            SimpleNamespace(
                id=self.job_id,
                paper_id=self.paper_id,
                paper_version_id=self.paper_version_id,
                stage=PipelineStage.SUMMARIZE_PAPER,
            )
        ]

    async def claim_failed_for_retry(self, job_id: object) -> bool:
        assert job_id == self.job_id
        return True

    async def claim_for_dispatch(self, job_id: object) -> int:
        assert job_id == self.job_id
        return 2

    async def release_dispatch(self, job_id: object) -> None:
        self.released.append(job_id)


class RecordingQueue:
    """Record one resumed ARQ dispatch."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _revision() -> ArxivObservedRevision:
    return ArxivObservedRevision(
        paper_id=uuid4(),
        paper_version_id=uuid4(),
        arxiv_id="2607.01234",
        version_number=1,
        version_created=True,
    )


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_seed_queue_failure_releases_lease_and_hides_diagnostics(monkeypatch) -> None:
    revision = _revision()
    paper = SimpleNamespace(processing_status=ProcessingStatus.METADATA_ONLY)
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = paper
    FakeJobRepository.released = []
    monkeypatch.setattr(onboarding_support, "PipelineJobRepository", FakeJobRepository)

    with pytest.raises(ApiError) as raised:
        asyncio.run(
            onboarding_support.enqueue_seed_downloads(
                session,
                FailingQueue(),
                (revision,),
            )
        )

    assert raised.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert raised.value.code == "queue_unavailable"
    assert "sensitive" not in raised.value.message
    assert len(FakeJobRepository.released) == 1
    assert paper.processing_status is ProcessingStatus.QUEUED
    assert session.commit.await_count == 3


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_existing_seed_resumes_failed_latest_revision_job(monkeypatch) -> None:
    session = AsyncMock(spec=AsyncSession)
    paper = SimpleNamespace(processing_status=ProcessingStatus.FAILED)
    session.get.return_value = paper
    queue = RecordingQueue()
    monkeypatch.setattr(onboarding_support, "PipelineJobRepository", FakeFailedJobRepository)

    resumed = asyncio.run(
        onboarding_support.resume_failed_seed_jobs(
            session,
            queue,
            (FakeFailedJobRepository.paper_id,),
        )
    )

    assert resumed == 1
    assert paper.processing_status is ProcessingStatus.QUEUED
    assert queue.calls == [
        (
            (
                PipelineStage.SUMMARIZE_PAPER.value,
                str(FakeFailedJobRepository.paper_id),
                str(FakeFailedJobRepository.paper_version_id),
            ),
            {
                "job_id": str(FakeFailedJobRepository.job_id),
                "_job_id": f"pipeline:{FakeFailedJobRepository.job_id}:attempt:2",
            },
        )
    ]
    assert session.commit.await_count == 2


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_existing_seed_resume_releases_failed_enqueue(monkeypatch) -> None:
    session = AsyncMock(spec=AsyncSession)
    session.get.return_value = SimpleNamespace(processing_status=ProcessingStatus.FAILED)
    FakeFailedJobRepository.released = []
    monkeypatch.setattr(onboarding_support, "PipelineJobRepository", FakeFailedJobRepository)

    with pytest.raises(ApiError) as raised:
        asyncio.run(
            onboarding_support.resume_failed_seed_jobs(
                session,
                FailingQueue(),
                (FakeFailedJobRepository.paper_id,),
            )
        )

    assert raised.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert raised.value.code == "queue_unavailable"
    assert "sensitive" not in raised.value.message
    assert FakeFailedJobRepository.released == [FakeFailedJobRepository.job_id]
    assert session.commit.await_count == 3


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_failed_seed_pipeline_returns_stable_public_error() -> None:
    paper_id = uuid4()
    rows = MagicMock()
    rows.all.return_value = [(paper_id, ProcessingStatus.FAILED)]
    session = AsyncMock(spec=AsyncSession)
    session.execute.return_value = rows

    with pytest.raises(ApiError) as raised:
        asyncio.run(onboarding_support.wait_for_seed_papers(session, (paper_id,)))

    assert raised.value.status_code == status.HTTP_502_BAD_GATEWAY
    assert raised.value.code == "seed_initialization_failed"
    assert raised.value.details is None
    session.rollback.assert_awaited_once()


@pytest.mark.base
@pytest.mark.api
@pytest.mark.pipeline
def test_internal_value_error_is_not_misclassified_as_invalid_input(monkeypatch) -> None:
    monkeypatch.setattr(onboarding, "ArxivClient", InternallyFailingArxivClient)

    with pytest.raises(ValueError, match="sensitive internal state"):
        asyncio.run(
            onboarding.initialize_from_seed(
                SeedInitializationRequest(arxiv_reference="2607.01234"),
                Principal(user_id=uuid4()),
                FailingQueue(),
                Settings(_env_file=None),
                AsyncMock(spec=AsyncSession),
            )
        )
