"""ARQ stages for downloading and parsing one exact paper revision."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.base import utc_now
from mneme.models.job import PipelineStage
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.repositories.job_identity import (
    chunk_idempotency_key,
    parse_idempotency_key,
    summarize_idempotency_key,
)
from mneme.services.documents import DocumentStorage, PdfDownloader, PdfParser, versioned_pdf_url
from mneme.tasks.document_runtime import (
    DocumentStageError,
    PendingEnqueue,
    ensure_child_job,
    run_document_stage,
)


async def _load_revision(
    session: AsyncSession, paper_id: UUID, paper_version_id: UUID
) -> tuple[Paper, PaperVersion]:
    statement = (
        select(Paper, PaperVersion)
        .join(PaperVersion, PaperVersion.paper_id == Paper.id)
        .where(Paper.id == paper_id, PaperVersion.id == paper_version_id)
        .with_for_update()
    )
    row = (await session.execute(statement)).one_or_none()
    if row is None:
        raise DocumentStageError(
            "paper_revision_not_found", "The requested paper revision does not exist."
        )
    return row[0], row[1]


async def download_pdf(
    ctx: dict[str, Any],
    paper_id: str,
    paper_version_id: str,
    *,
    job_id: str,
) -> str:
    """Download one immutable arXiv revision and queue its parse stage."""
    storage: DocumentStorage = ctx["document_storage"]
    downloader: PdfDownloader = ctx["pdf_downloader"]
    parser: PdfParser = ctx["pdf_parser"]

    async def runner(
        session: AsyncSession, resolved_paper_id: UUID, resolved_version_id: UUID
    ) -> list[PendingEnqueue]:
        paper, version = await _load_revision(session, resolved_paper_id, resolved_version_id)
        destination = storage.paths_for(resolved_paper_id, resolved_version_id).source_pdf
        result = await downloader.download(
            url=versioned_pdf_url(paper.arxiv_id, version.version_number),
            destination=destination,
            expected_checksum=version.source_checksum,
        )
        version.source_checksum = result.checksum
        version.source_size_bytes = result.byte_size
        version.downloaded_at = utc_now()
        paper.processing_status = ProcessingStatus.PROCESSING
        child = await ensure_child_job(
            session,
            stage=PipelineStage.PARSE_PDF,
            function="parse_pdf",
            paper_id=resolved_paper_id,
            paper_version_id=resolved_version_id,
            idempotency_key=parse_idempotency_key(
                paper_id=resolved_paper_id,
                paper_version_id=resolved_version_id,
                source_checksum=result.checksum,
                parser_version=parser.parser_version,
            ),
        )
        return [child] if child is not None else []

    return await run_document_stage(
        ctx,
        stage=PipelineStage.DOWNLOAD_PDF,
        job_id=job_id,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        runner=runner,
    )


def _source_digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    byte_size = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(block)
            byte_size += len(block)
    return digest.hexdigest(), byte_size


async def parse_pdf(
    ctx: dict[str, Any],
    paper_id: str,
    paper_version_id: str,
    *,
    job_id: str,
) -> str:
    """Parse one stored PDF, persist its sidecar, and fan out by durable IDs."""
    storage: DocumentStorage = ctx["document_storage"]
    parser: PdfParser = ctx["pdf_parser"]

    async def runner(
        session: AsyncSession, resolved_paper_id: UUID, resolved_version_id: UUID
    ) -> list[PendingEnqueue]:
        paper, version = await _load_revision(session, resolved_paper_id, resolved_version_id)
        if (
            version.source_checksum is None
            or version.source_size_bytes is None
            or version.downloaded_at is None
        ):
            raise DocumentStageError(
                "source_provenance_incomplete",
                "The source PDF has not completed its download stage.",
            )
        source_path = storage.paths_for(resolved_paper_id, resolved_version_id).source_pdf
        if not source_path.is_file():
            raise DocumentStageError("source_pdf_missing", "The stored source PDF is missing.")
        checksum, byte_size = await asyncio.to_thread(_source_digest, source_path)
        if checksum != version.source_checksum or byte_size != version.source_size_bytes:
            raise DocumentStageError(
                "source_checksum_mismatch",
                "The stored source PDF does not match its persisted provenance.",
            )

        parsed_at = utc_now()
        # The combined PyMuPDF/pdfplumber parser deadlocks under to_thread in
        # the supported runtime, so bounded ARQ workers execute it directly.
        document = parser.parse(
            source_path,
            paper_id=resolved_paper_id,
            paper_version_id=resolved_version_id,
            source_checksum=checksum,
            abstract=paper.abstract,
            parsed_at=parsed_at,
        )
        artifact = await asyncio.to_thread(
            storage.write_parsed_document,
            resolved_paper_id,
            resolved_version_id,
            document,
        )
        version.parsed_checksum = artifact.checksum
        version.parser_version = document.parser_version
        version.parse_quality = document.parse_quality
        version.parsed_at = document.parsed_at
        paper.processing_status = ProcessingStatus.PARTIAL

        children: list[PendingEnqueue] = []
        identities = (
            (
                PipelineStage.SUMMARIZE_PAPER,
                "summarize_paper",
                summarize_idempotency_key(
                    paper_id=resolved_paper_id,
                    paper_version_id=resolved_version_id,
                    parsed_checksum=artifact.checksum,
                    parser_version=document.parser_version,
                ),
            ),
            (
                PipelineStage.CHUNK_PAPER,
                "chunk_paper",
                chunk_idempotency_key(
                    paper_id=resolved_paper_id,
                    paper_version_id=resolved_version_id,
                    parsed_checksum=artifact.checksum,
                    parser_version=document.parser_version,
                ),
            ),
        )
        for stage, function, idempotency_key in identities:
            child = await ensure_child_job(
                session,
                stage=stage,
                function=function,
                paper_id=resolved_paper_id,
                paper_version_id=resolved_version_id,
                idempotency_key=idempotency_key,
            )
            if child is not None:
                children.append(child)
        return children

    return await run_document_stage(
        ctx,
        stage=PipelineStage.PARSE_PDF,
        job_id=job_id,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        runner=runner,
    )
