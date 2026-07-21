"""Focused tests for durable document-stage ARQ jobs."""

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ParseQuality
from mneme.services.documents import (
    ParsedDocument,
    ParsedSection,
    PdfDownloadResult,
)
from mneme.tasks import document_jobs, document_runtime

PAPER_ID = UUID("00000000-0000-0000-0000-000000000111")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000222")
JOB_ID = UUID("00000000-0000-0000-0000-000000000333")
SOURCE = b"%PDF-1.7\nexact revision\n"
SOURCE_CHECKSUM = hashlib.sha256(SOURCE).hexdigest()

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


class FakeSession:
    """Minimal transaction tracker used by the stage harness."""

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
    def __init__(self) -> None:
        self.session = FakeSession()

    def session_factory(self) -> FakeSession:
        return self.session


class FakeJobRepository:
    """Shared in-memory job registry for parent and child operations."""

    def __init__(self, parent: PipelineJob) -> None:
        self.jobs = {parent.id: parent}
        self.created: list[PipelineJob] = []

    async def get(self, job_id: UUID) -> PipelineJob | None:
        return self.jobs.get(job_id)

    async def get_or_create(self, **values: Any) -> tuple[PipelineJob, bool]:
        key = values["idempotency_key"]
        for existing in self.jobs.values():
            if existing.idempotency_key == key:
                return existing, False
        job = PipelineJob(
            id=uuid4(),
            idempotency_key=key,
            stage=values["stage"],
            paper_id=values["paper_id"],
            paper_version_id=values["paper_version_id"],
            pipeline_version="v1",
            status=JobStatus.QUEUED,
            attempt_count=0,
        )
        self.jobs[job.id] = job
        self.created.append(job)
        return job, True

    async def requeue(self, job: PipelineJob) -> PipelineJob:
        job.status = JobStatus.QUEUED
        return job

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
        job.dispatched_at = datetime.now(UTC)
        return job.attempt_count + 1

    async def release_dispatch(self, job_id: UUID) -> None:
        self.jobs[job_id].dispatched_at = None

    async def mark_running(self, job_id: UUID) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.RUNNING
        job.attempt_count += 1

    async def mark_succeeded(self, job_id: UUID) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.SUCCEEDED
        job.error_code = None
        job.last_error = None

    async def mark_failed(self, job_id: UUID, *, error_code: str, message: str) -> None:
        job = self.jobs[job_id]
        job.status = JobStatus.FAILED
        job.error_code = error_code
        job.last_error = message


class FakeQueue:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> SimpleNamespace:
        self.calls.append((function, args, kwargs))
        return SimpleNamespace()


class FakeDownloader:
    async def download(
        self, *, url: str, destination: Path, expected_checksum: str | None
    ) -> PdfDownloadResult:
        assert url == "https://arxiv.org/pdf/2607.00001v2"
        assert expected_checksum is None
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(SOURCE)
        return PdfDownloadResult(destination, SOURCE_CHECKSUM, len(SOURCE), reused=False)


class FakeParser:
    parser_version = "fake-parser-v1"

    def parse(
        self,
        source_path: Path,
        *,
        paper_id: UUID,
        paper_version_id: UUID,
        source_checksum: str,
        abstract: str,
        parsed_at: datetime,
    ) -> ParsedDocument:
        assert source_path.read_bytes() == SOURCE
        assert abstract == "Fallback abstract"
        return ParsedDocument(
            parser_version=self.parser_version,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            source_checksum=source_checksum,
            parse_quality=ParseQuality.ABSTRACT_ONLY,
            page_count=0,
            sections=[ParsedSection(title="Abstract", text=abstract)],
            fallback_reason="insufficient_text",
            parsed_at=parsed_at,
        )


def _parent_job(stage: PipelineStage) -> PipelineJob:
    return PipelineJob(
        id=JOB_ID,
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        idempotency_key=f"v1:{stage.value}:{'a' * 64}",
        stage=stage,
        status=JobStatus.QUEUED,
        attempt_count=0,
        pipeline_version="v1",
    )


def _revision(*, downloaded: bool = False) -> tuple[Paper, PaperVersion]:
    paper = Paper(
        id=PAPER_ID,
        arxiv_id="2607.00001",
        title="Paper",
        abstract="Fallback abstract",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001v2",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        source_updated_at=datetime(2026, 7, 2, tzinfo=UTC),
    )
    version = PaperVersion(
        id=VERSION_ID,
        paper_id=PAPER_ID,
        version_number=2,
        source_checksum=SOURCE_CHECKSUM if downloaded else None,
        source_size_bytes=len(SOURCE) if downloaded else None,
        downloaded_at=datetime(2026, 7, 21, tzinfo=UTC) if downloaded else None,
    )
    return paper, version


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    parent: PipelineJob,
    revision: tuple[Paper, PaperVersion],
) -> tuple[dict[str, Any], FakeJobRepository, FakeQueue]:
    repository = FakeJobRepository(parent)
    queue = FakeQueue()

    async def load_revision(*args: object) -> tuple[Paper, PaperVersion]:
        return revision

    async def run_inline(function: Any, *args: object, **kwargs: object) -> Any:
        return function(*args, **kwargs)

    monkeypatch.setattr(document_runtime, "PipelineJobRepository", lambda session: repository)
    monkeypatch.setattr(document_jobs, "_load_revision", load_revision)
    monkeypatch.setattr(document_jobs.asyncio, "to_thread", run_inline)
    context: dict[str, Any] = {"database": FakeDatabase(), "redis": queue}
    return context, repository, queue
