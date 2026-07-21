"""Revision-safe ARQ jobs for summarization, chunking, and embedding."""

from typing import Any
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.pipeline import (
    PaperNotReadyError,
    chunk_paper_stage,
    embed_chunks_stage,
    summarize_paper_stage,
)
from mneme.ai.types import ProviderNotConfiguredError
from mneme.core.config import Settings
from mneme.models.job import PipelineStage
from mneme.models.paper import PaperVersion, ParseQuality
from mneme.repositories.job_identity import embed_idempotency_key
from mneme.services.processing_status import reconcile_processing_status
from mneme.tasks.ai_runtime import load_parsed_document, run_ai_stage
from mneme.tasks.document_runtime import (
    DocumentStageError,
    PendingEnqueue,
    dispatch_pending,
    ensure_child_job,
)

logger = structlog.get_logger(__name__)


async def summarize_paper(
    ctx: dict[str, Any],
    paper_id: str,
    paper_version_id: str,
    *,
    job_id: str | None = None,
) -> str:
    """Generate a structured summary from one persisted parser sidecar."""
    resolved_paper_id = UUID(paper_id)
    resolved_version_id = UUID(paper_version_id)

    async def runner(session: AsyncSession) -> object:
        document = await load_parsed_document(
            ctx, paper_id=resolved_paper_id, paper_version_id=resolved_version_id
        )
        body = None
        if document.parse_quality is not ParseQuality.ABSTRACT_ONLY:
            body = "\n\n".join(section.text for section in document.sections)
        summary = await summarize_paper_stage(
            session,
            paper_id=resolved_paper_id,
            paper_version_id=resolved_version_id,
            summarizer=ctx["summarizer"],
            body=body,
        )
        await reconcile_processing_status(
            session, paper_id=resolved_paper_id, paper_version_id=resolved_version_id
        )
        return summary

    return await run_ai_stage(
        ctx,
        stage=PipelineStage.SUMMARIZE_PAPER,
        job_id=job_id,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        runner=runner,
    )


async def chunk_paper(
    ctx: dict[str, Any],
    paper_id: str,
    paper_version_id: str,
    *,
    job_id: str | None = None,
) -> str:
    """Chunk one parser sidecar and durably schedule exact-revision embedding."""
    settings: Settings = ctx["settings"]
    resolved_paper_id = UUID(paper_id)
    resolved_version_id = UUID(paper_version_id)
    pending: PendingEnqueue | None = None

    async def runner(session: AsyncSession) -> object:
        nonlocal pending
        document = await load_parsed_document(
            ctx, paper_id=resolved_paper_id, paper_version_id=resolved_version_id
        )
        count = await chunk_paper_stage(
            session,
            paper_id=resolved_paper_id,
            paper_version_id=resolved_version_id,
            sections=document.sections,
            max_tokens=settings.ai_chunk_max_tokens,
            overlap_tokens=settings.ai_chunk_overlap_tokens,
        )
        version = await session.get(PaperVersion, resolved_version_id)
        if (
            version is None
            or version.paper_id != resolved_paper_id
            or version.parsed_checksum is None
            or version.parser_version is None
        ):
            raise PaperNotReadyError("The parsed revision provenance is incomplete.")
        pending = await ensure_child_job(
            session,
            stage=PipelineStage.EMBED_CHUNKS,
            function="embed_chunks",
            paper_id=resolved_paper_id,
            paper_version_id=resolved_version_id,
            idempotency_key=embed_idempotency_key(
                paper_id=resolved_paper_id,
                paper_version_id=resolved_version_id,
                parsed_checksum=version.parsed_checksum,
                parser_version=version.parser_version,
                embedding_model=settings.ai_embedding_model,
            ),
        )
        await reconcile_processing_status(
            session, paper_id=resolved_paper_id, paper_version_id=resolved_version_id
        )
        return count

    outcome = await run_ai_stage(
        ctx,
        stage=PipelineStage.CHUNK_PAPER,
        job_id=job_id,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        runner=runner,
    )
    if outcome == "ok" and pending is not None:
        async with ctx["database"].session_factory() as session:
            try:
                await dispatch_pending(ctx, session, [pending])
            except DocumentStageError:
                logger.warning("embedding_dispatch_deferred", job_id=str(pending.job_id))
    return outcome


async def embed_chunks(
    ctx: dict[str, Any],
    paper_id: str,
    paper_version_id: str,
    *,
    job_id: str | None = None,
) -> str:
    """Embed every unembedded chunk of one exact revision."""
    resolved_paper_id = UUID(paper_id)
    resolved_version_id = UUID(paper_version_id)

    async def runner(session: AsyncSession) -> object:
        embedder = ctx.get("embedder")
        if embedder is None:
            raise ProviderNotConfiguredError(
                "No embedding provider is configured (missing OpenAI API key)."
            )
        embedded = await embed_chunks_stage(
            session,
            paper_id=resolved_paper_id,
            paper_version_id=resolved_version_id,
            embedder=embedder,
        )
        await reconcile_processing_status(
            session, paper_id=resolved_paper_id, paper_version_id=resolved_version_id
        )
        return embedded

    return await run_ai_stage(
        ctx,
        stage=PipelineStage.EMBED_CHUNKS,
        job_id=job_id,
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        runner=runner,
    )
