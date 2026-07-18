"""Idempotent AI pipeline stages: summarize, chunk, and embed.

Each stage takes an open session plus the AI services it needs, so the ARQ
wrappers in ``mneme.tasks.ai_jobs`` stay thin and tests can drive stages
directly with fakes. Stages are safe to retry: re-running with unchanged
input reuses stored artifacts instead of spending tokens again.
"""

from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.chunking import ParsedSection, chunk_sections
from mneme.ai.embeddings import EmbeddingService
from mneme.ai.prompts import SUMMARY_PROMPT_VERSION
from mneme.ai.summarization import SummarizationService, summary_input_hash
from mneme.models.artifact import PaperSummary
from mneme.models.paper import Paper, ProcessingStatus
from mneme.repositories.artifacts import ArtifactRepository, ChunkEmbeddingUpdate

logger = structlog.get_logger(__name__)


class PaperNotReadyError(RuntimeError):
    """The paper or revision required by a stage does not exist yet."""


async def _require_paper(session: AsyncSession, paper_id: UUID) -> Paper:
    paper = await session.get(Paper, paper_id)
    if paper is None:
        raise PaperNotReadyError(f"Paper {paper_id} does not exist.")
    return paper


async def summarize_paper_stage(
    session: AsyncSession,
    *,
    paper_id: UUID,
    summarizer: SummarizationService,
    body: str | None = None,
) -> PaperSummary:
    """Generate and store one structured summary for the latest revision.

    ``body`` is the parse stage's extracted text; when absent the abstract is
    summarized instead (the parse fallback path). Idempotent on the exact
    (revision, input, provider, model, prompt version) identity.
    """
    paper = await _require_paper(session, paper_id)
    artifacts = ArtifactRepository(session)
    version = await artifacts.get_latest_version(paper_id)
    if version is None:
        raise PaperNotReadyError(f"Paper {paper_id} has no observed revision.")

    text = body if body is not None and body.strip() else paper.abstract
    input_hash = summary_input_hash(title=paper.title, body=text[: summarizer.max_input_chars])
    existing = await artifacts.find_summary_by_input(
        paper_version_id=version.id,
        input_hash=input_hash,
        prompt_version=SUMMARY_PROMPT_VERSION,
    )
    if existing is not None:
        logger.info("summary_already_stored", paper_id=str(paper_id), input_hash=input_hash)
        return existing

    result = await summarizer.summarize(title=paper.title, abstract=paper.abstract, body=body)
    generation = PaperSummary(
        paper_id=paper_id,
        paper_version_id=version.id,
        status=result.status,
        content=result.summary.model_dump(mode="json"),
        provider=result.completion.provider.value,
        model_snapshot=result.completion.model,
        prompt_version=result.completion.prompt_version,
        input_hash=result.input_hash,
        estimated_cost=result.completion.estimated_cost,
        generation_parameters={"max_output_tokens": summarizer.max_output_tokens},
        input_tokens=result.completion.usage.input_tokens,
        output_tokens=result.completion.usage.output_tokens,
        latency_ms=result.completion.latency_ms,
    )
    stored = await artifacts.add_summary(generation)
    if paper.processing_status in (ProcessingStatus.METADATA_ONLY, ProcessingStatus.QUEUED):
        paper.processing_status = ProcessingStatus.PARTIAL
    logger.info(
        "summary_stored",
        paper_id=str(paper_id),
        status=stored.status.value,
        cached=result.completion.cached,
        estimated_cost_usd=str(stored.estimated_cost),
    )
    return stored


async def chunk_paper_stage(
    session: AsyncSession,
    *,
    paper_id: UUID,
    sections: list[ParsedSection],
    max_tokens: int,
    overlap_tokens: int,
) -> int:
    """Chunk parsed sections for the latest revision; returns the chunk count.

    Re-running replaces the revision's chunks with identical content (same
    hashes), so downstream embedding stays consistent.
    """
    await _require_paper(session, paper_id)
    artifacts = ArtifactRepository(session)
    version = await artifacts.get_latest_version(paper_id)
    if version is None:
        raise PaperNotReadyError(f"Paper {paper_id} has no observed revision.")

    drafts = chunk_sections(sections, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    stored = await artifacts.replace_chunks(
        paper_id=paper_id, paper_version_id=version.id, drafts=drafts
    )
    logger.info("chunks_stored", paper_id=str(paper_id), chunks=len(stored))
    return len(stored)


async def embed_chunks_stage(
    session: AsyncSession,
    *,
    paper_id: UUID,
    embedder: EmbeddingService,
    batch_limit: int = 512,
) -> int:
    """Embed all unembedded chunks of the latest revision; returns the count.

    Only chunks without vectors are fetched, so retries after a partial
    failure resume where the previous attempt stopped.
    """
    paper = await _require_paper(session, paper_id)
    artifacts = ArtifactRepository(session)
    version = await artifacts.get_latest_version(paper_id)
    if version is None:
        raise PaperNotReadyError(f"Paper {paper_id} has no observed revision.")

    embedded = 0
    while True:
        chunks = await artifacts.list_chunks_without_embedding(
            paper_version_id=version.id, limit=batch_limit
        )
        if not chunks:
            break
        vectors = await embedder.embed_texts([chunk.content for chunk in chunks])
        await artifacts.set_chunk_embeddings(
            [
                ChunkEmbeddingUpdate(
                    chunk_id=chunk.id, embedding=vector, embedding_model=embedder.model
                )
                for chunk, vector in zip(chunks, vectors, strict=True)
            ]
        )
        embedded += len(chunks)

    if embedded and paper.processing_status is not ProcessingStatus.READY:
        paper.processing_status = ProcessingStatus.READY
    logger.info("chunks_embedded", paper_id=str(paper_id), chunks=embedded)
    return embedded
