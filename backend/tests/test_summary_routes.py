"""Contract tests for the Milestone 2 summary endpoint (cached or async)."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.ai import (
    get_artifact_repository,
    get_pipeline_job_repository,
    get_task_queue,
)
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.summaries import router as summaries_router
from mneme.db.dependencies import get_session
from mneme.models.artifact import PaperSummary, SourceMatchStatus, SummaryStatus
from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ParseQuality, ProcessingStatus
from mneme.repositories.job_identity import summarize_idempotency_key

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
PAPER_ID = UUID("00000000-0000-0000-0000-000000000222")
JOB_ID = UUID("00000000-0000-0000-0000-000000000333")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000444")
TIMESTAMP = datetime(2026, 7, 15, 8, 30, tzinfo=UTC)
ABSTRACT = (
    "We introduce a grounded assistant. It cites sources for every claim. "
    "Extensive experiments show strong results."
)
PARSED_CHECKSUM = "b" * 64
PARSER_VERSION = "test-parser-v1"


def _paper() -> Paper:
    return Paper(
        id=PAPER_ID,
        arxiv_id="2607.00001",
        title="Grounded Research",
        abstract=ABSTRACT,
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        source_license=None,
        processing_status=ProcessingStatus.METADATA_ONLY,
        published_at=TIMESTAMP,
        source_updated_at=TIMESTAMP,
    )


def _stored_summary() -> PaperSummary:
    return PaperSummary(
        id=uuid4(),
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        status=SummaryStatus.READY,
        source_match_status=SourceMatchStatus.NOT_CHECKED,
        content={
            "tldr": "A grounded assistant that cites sources.",
            "key_claims": ["Grounded answers improve trust."],
            "methodology": "Retrieval plus citation checking.",
            "limitations": "Single-paper scope.",
        },
        provider="anthropic",
        model_snapshot="claude-opus-4-8",
        prompt_version="summary-v1",
        input_hash="a" * 64,
        created_at=TIMESTAMP,
    )


def _version(*, downloaded: bool = True, parsed: bool = True) -> PaperVersion:
    return PaperVersion(
        id=VERSION_ID,
        paper_id=PAPER_ID,
        version_number=1,
        source_checksum="a" * 64 if downloaded else None,
        source_size_bytes=100 if downloaded else None,
        downloaded_at=TIMESTAMP if downloaded else None,
        parsed_checksum=PARSED_CHECKSUM if parsed else None,
        parser_version=PARSER_VERSION if parsed else None,
        parse_quality=ParseQuality.TEXT_ONLY if parsed else None,
        parsed_at=TIMESTAMP if parsed else None,
    )


def _job(status: JobStatus = JobStatus.QUEUED) -> PipelineJob:
    return PipelineJob(
        id=JOB_ID,
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        idempotency_key=summarize_idempotency_key(
            paper_id=PAPER_ID,
            paper_version_id=VERSION_ID,
            parsed_checksum=PARSED_CHECKSUM,
            parser_version=PARSER_VERSION,
        ),
        stage=PipelineStage.SUMMARIZE_PAPER,
        status=status,
        attempt_count=0,
        pipeline_version="v1",
        updated_at=TIMESTAMP,
    )


class FakePaperCatalogRepository:
    """Single-paper catalog fake."""

    def __init__(self, paper: Paper | None) -> None:
        self.paper = paper

    async def get_paper(self, paper_id: UUID) -> Paper | None:
        if self.paper is not None and self.paper.id == paper_id:
            return self.paper
        return None


class FakeArtifactRepository:
    """Stored-summary lookup fake."""

    def __init__(
        self,
        summary: PaperSummary | None,
        *,
        version: PaperVersion | None = None,
        has_version: bool = True,
    ) -> None:
        self.summary = summary
        self.version = version or _version()
        self.has_version = has_version

    async def get_summary_for_version(self, paper_version_id: UUID) -> PaperSummary | None:
        if self.summary is not None and self.summary.paper_version_id == paper_version_id:
            return self.summary
        return None

    async def get_latest_version(self, paper_id: UUID) -> PaperVersion | None:
        if self.has_version and self.version.paper_id == paper_id:
            return self.version
        return None


class FakeJobRepository:
    """In-memory pipeline job fake."""

    def __init__(self, existing: PipelineJob | None = None) -> None:
        self.existing = existing
        self.retry_claims: list[UUID] = []
        self.dispatch_claims: list[UUID] = []
        self.released: list[UUID] = []
        self.create_calls: list[tuple[str, PipelineStage, UUID | None, UUID | None]] = []

    async def get_or_create(
        self,
        *,
        idempotency_key: str,
        stage: PipelineStage,
        paper_id: UUID | None,
        paper_version_id: UUID | None,
    ) -> tuple[PipelineJob, bool]:
        self.create_calls.append((idempotency_key, stage, paper_id, paper_version_id))
        if self.existing is not None:
            return self.existing, False
        return _job(), True

    async def get(self, job_id: UUID) -> PipelineJob | None:
        if self.existing is not None and self.existing.id == job_id:
            return self.existing
        return _job() if job_id == JOB_ID else None

    async def claim_failed_for_retry(self, job_id: UUID) -> bool:
        if self.existing is None or self.existing.status is not JobStatus.FAILED:
            return False
        self.retry_claims.append(job_id)
        self.existing.status = JobStatus.QUEUED
        return True

    async def claim_for_dispatch(self, job_id: UUID, *, lease_seconds: int = 300) -> int | None:
        del lease_seconds
        job = await self.get(job_id)
        if job is None or job.status is not JobStatus.QUEUED or job.dispatched_at is not None:
            return None
        self.dispatch_claims.append(job_id)
        job.dispatched_at = TIMESTAMP
        return job.attempt_count + 1

    async def release_dispatch(self, job_id: UUID) -> None:
        self.released.append(job_id)


class FakeQueue:
    """Recording ARQ enqueue fake."""

    def __init__(self, *, fail: bool = False) -> None:
        self.enqueued: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        self.fail = fail

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> None:
        if self.fail:
            raise RuntimeError("queue unavailable")
        self.enqueued.append((function, args, kwargs))


class FakeSession:
    """Commit-counting session stand-in."""

    def __init__(self) -> None:
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


def _application(
    catalog: FakePaperCatalogRepository,
    artifacts: FakeArtifactRepository,
    jobs: FakeJobRepository,
    queue: FakeQueue,
) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    async def catalog_override() -> FakePaperCatalogRepository:
        return catalog

    async def artifacts_override() -> FakeArtifactRepository:
        return artifacts

    async def jobs_override() -> FakeJobRepository:
        return jobs

    async def queue_override() -> FakeQueue:
        return queue

    async def session_override() -> FakeSession:
        return FakeSession()

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(summaries_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_paper_catalog_repository] = catalog_override
    application.dependency_overrides[get_artifact_repository] = artifacts_override
    application.dependency_overrides[get_pipeline_job_repository] = jobs_override
    application.dependency_overrides[get_task_queue] = queue_override
    application.dependency_overrides[get_session] = session_override
    return application


async def _get(application: FastAPI, path: str) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.base
@pytest.mark.api
def test_stored_summary_is_served_with_frozen_contract_fields() -> None:
    application = _application(
        FakePaperCatalogRepository(_paper()),
        FakeArtifactRepository(_stored_summary()),
        FakeJobRepository(),
        FakeQueue(),
    )

    response = asyncio.run(_get(application, f"/v1/papers/{PAPER_ID}/summary"))

    assert response.status_code == 200
    assert response.json() == {
        "paper_id": str(PAPER_ID),
        "status": "ready",
        "tldr": "A grounded assistant that cites sources.",
        "key_claims": ["Grounded answers improve trust."],
        "methodology": "Retrieval plus citation checking.",
        "limitations": "Single-paper scope.",
        "source_match_status": "not_checked",
    }


@pytest.mark.base
@pytest.mark.api
def test_missing_summary_enqueues_generation_and_returns_job() -> None:
    queue = FakeQueue()
    application = _application(
        FakePaperCatalogRepository(_paper()),
        FakeArtifactRepository(None),
        FakeJobRepository(),
        queue,
    )

    response = asyncio.run(_get(application, f"/v1/papers/{PAPER_ID}/summary"))

    assert response.status_code == 202
    payload = response.json()
    assert payload["id"] == str(JOB_ID)
    assert payload["stage"] == "summarize_paper"
    assert payload["status"] == "queued"
    assert len(queue.enqueued) == 1
    function, args, kwargs = queue.enqueued[0]
    assert function == "summarize_paper"
    assert args == (str(PAPER_ID), str(VERSION_ID))
    assert kwargs["job_id"] == str(JOB_ID)
    assert kwargs["_job_id"] == f"pipeline:{JOB_ID}:attempt:1"


@pytest.mark.base
@pytest.mark.api
def test_pending_job_is_returned_without_a_duplicate_enqueue() -> None:
    queue = FakeQueue()
    application = _application(
        FakePaperCatalogRepository(_paper()),
        FakeArtifactRepository(None),
        FakeJobRepository(existing=_job(JobStatus.RUNNING)),
        queue,
    )

    response = asyncio.run(_get(application, f"/v1/papers/{PAPER_ID}/summary"))

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    assert queue.enqueued == []


@pytest.mark.base
@pytest.mark.api
def test_failed_job_is_requeued_on_retry() -> None:
    queue = FakeQueue()
    jobs = FakeJobRepository(existing=_job(JobStatus.FAILED))
    application = _application(
        FakePaperCatalogRepository(_paper()),
        FakeArtifactRepository(None),
        jobs,
        queue,
    )

    response = asyncio.run(_get(application, f"/v1/papers/{PAPER_ID}/summary"))

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert jobs.retry_claims == [JOB_ID]
    assert len(queue.enqueued) == 1


@pytest.mark.base
@pytest.mark.api
def test_unknown_paper_returns_stable_not_found_error() -> None:
    application = _application(
        FakePaperCatalogRepository(None),
        FakeArtifactRepository(None),
        FakeJobRepository(),
        FakeQueue(),
    )

    response = asyncio.run(_get(application, f"/v1/papers/{uuid4()}/summary"))

    assert response.status_code == 404
    payload = response.json()
    assert payload["code"] == "paper_not_found"
    assert "request_id" in payload
