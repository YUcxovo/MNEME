"""Focused tests for durable document-stage ARQ jobs."""

import asyncio
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.models.paper import Paper, PaperVersion, ParseQuality, ProcessingStatus
from mneme.services.documents import (
    DocumentStorage,
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
    context: dict[str, Any] = {
        "database": FakeDatabase(),
        "redis": queue,
        "pdf_parser": FakeParser(),
    }
    return context, repository, queue


def test_download_persists_provenance_before_dispatching_parse(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paper, version = _revision()
    parent = _parent_job(PipelineStage.DOWNLOAD_PDF)
    context, repository, queue = _install_fakes(monkeypatch, parent, (paper, version))
    context.update(document_storage=DocumentStorage(tmp_path), pdf_downloader=FakeDownloader())

    outcome = asyncio.run(
        document_jobs.download_pdf(context, str(PAPER_ID), str(VERSION_ID), job_id=str(JOB_ID))
    )

    assert outcome == "ok"
    assert parent.status is JobStatus.SUCCEEDED
    assert version.source_checksum == SOURCE_CHECKSUM
    assert version.source_size_bytes == len(SOURCE)
    assert version.downloaded_at is not None
    assert [job.stage for job in repository.created] == [PipelineStage.PARSE_PDF]
    function, args, kwargs = queue.calls[0]
    assert function == "parse_pdf"
    assert args == (str(PAPER_ID), str(VERSION_ID))
    assert kwargs["job_id"] == str(repository.created[0].id)
    assert kwargs["_job_id"] == f"pipeline:{repository.created[0].id}:attempt:1"


def test_abstract_fallback_is_stored_and_fans_out_by_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    paper, version = _revision(downloaded=True)
    storage = DocumentStorage(tmp_path)
    storage.write_source_pdf(PAPER_ID, VERSION_ID, SOURCE)
    parent = _parent_job(PipelineStage.PARSE_PDF)
    context, repository, queue = _install_fakes(monkeypatch, parent, (paper, version))
    context.update(document_storage=storage, pdf_parser=FakeParser())

    outcome = asyncio.run(
        document_jobs.parse_pdf(context, str(PAPER_ID), str(VERSION_ID), job_id=str(JOB_ID))
    )

    assert outcome == "ok"
    parsed = storage.read_parsed_document(PAPER_ID, VERSION_ID)
    assert parsed.parse_quality is ParseQuality.ABSTRACT_ONLY
    assert version.parsed_checksum is not None
    assert version.parser_version == "fake-parser-v1"
    assert version.parse_quality is ParseQuality.ABSTRACT_ONLY
    assert paper.processing_status is ProcessingStatus.PROCESSING
    assert [job.stage for job in repository.created] == [
        PipelineStage.SUMMARIZE_PAPER,
        PipelineStage.CHUNK_PAPER,
    ]
    assert [call[0] for call in queue.calls] == ["summarize_paper", "chunk_paper"]
    assert all(call[1] == (str(PAPER_ID), str(VERSION_ID)) for call in queue.calls)
    assert all("sections" not in call[2] and "body" not in call[2] for call in queue.calls)
    assert queue.calls[0][2]["_job_id"] != queue.calls[1][2]["_job_id"]


def test_unexpected_failure_is_recorded_before_it_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _parent_job(PipelineStage.PARSE_PDF)
    context, _, _ = _install_fakes(monkeypatch, parent, _revision(downloaded=True))

    async def crash(*args: object) -> list[document_runtime.PendingEnqueue]:
        raise RuntimeError("unsafe implementation detail")

    with pytest.raises(RuntimeError, match="unsafe implementation detail"):
        asyncio.run(
            document_runtime.run_document_stage(
                context,
                stage=PipelineStage.PARSE_PDF,
                job_id=str(JOB_ID),
                paper_id=str(PAPER_ID),
                paper_version_id=str(VERSION_ID),
                runner=crash,
            )
        )

    assert parent.status is JobStatus.FAILED
    assert parent.error_code == "document_stage_error"
    assert parent.last_error == "The document pipeline stage failed unexpectedly."


def test_mismatched_job_identity_is_rejected_without_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = _parent_job(PipelineStage.DOWNLOAD_PDF)
    context, _, _ = _install_fakes(monkeypatch, parent, _revision())

    async def unused(*args: object) -> list[document_runtime.PendingEnqueue]:
        raise AssertionError("runner must not be called")

    outcome = asyncio.run(
        document_runtime.run_document_stage(
            context,
            stage=PipelineStage.PARSE_PDF,
            job_id=str(JOB_ID),
            paper_id=str(PAPER_ID),
            paper_version_id=str(VERSION_ID),
            runner=unused,
        )
    )

    assert outcome == "pipeline_job_identity_mismatch"
    assert parent.status is JobStatus.QUEUED
