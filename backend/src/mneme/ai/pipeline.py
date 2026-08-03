"""Idempotent AI pipeline stages: summarize, chunk, and embed.

Each stage takes an open session plus the AI services it needs, so the ARQ
wrappers in ``mneme.tasks.ai_jobs`` stay thin and tests can drive stages
directly with fakes. Stages are safe to retry: re-running with unchanged
input reuses stored artifacts instead of spending tokens again.
"""

from collections.abc import Sequence
from typing import cast
from uuid import UUID

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.chunking import ParsedSection, chunk_sections
from mneme.ai.claim_provenance import ChunkSource, match_claims, provenance_status
from mneme.ai.embeddings import EmbeddingService
from mneme.ai.prompts import SUMMARY_PROMPT_VERSION
from mneme.ai.summarization import StructuredSummary, SummarizationService, summary_input_hash
from mneme.models.artifact import PaperSummary, SourceMatchStatus
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.repositories.artifacts import ArtifactRepository, ChunkEmbeddingUpdate

logger = structlog.get_logger(__name__)


class PaperNotReadyError(RuntimeError):
    """The paper or revision required by a stage does not exist yet."""


async def _require_paper_version(
    session: AsyncSession, *, paper_id: UUID, paper_version_id: UUID
) -> tuple[Paper, PaperVersion]:
    """Return one exact paper revision or reject a mismatched stage identity."""
    paper = await session.get(Paper, paper_id, with_for_update=True)
    if paper is None:
        raise PaperNotReadyError(f"Paper {paper_id} does not exist.")
    version = await session.get(PaperVersion, paper_version_id)
    if version is None or version.paper_id != paper_id:
        raise PaperNotReadyError(
            f"Paper version {paper_version_id} does not belong to paper {paper_id}."
        )
    return paper, version


def _attach_claim_provenance(summary: PaperSummary, chunks: Sequence[ChunkSource]) -> bool:
    """Match a stored summary's key claims to one revision's chunks.

    Deterministic and safe to rerun: identical inputs produce identical
    provenance. Summaries without key claims stay ``not_checked``. Returns
    whether the stored row changed.
    """
    if not chunks:
        return False
    content = StructuredSummary.model_validate(summary.content)
    if not content.key_claims:
        return False
    claims = match_claims(content.key_claims, chunks)
    status = provenance_status(claims)
    updated = content.model_copy(update={"claims": claims}).model_dump(mode="json")
    if summary.content == updated and summary.source_match_status is status:
        return False
    summary.content = updated
    summary.source_match_status = status
    logger.info(
        "summary_claim_provenance_attached",
        paper_id=str(summary.paper_id),
        paper_version_id=str(summary.paper_version_id),
        claims=len(claims),
        matched=sum(1 for claim in claims if claim.matched),
        source_match_status=status.value,
    )
    return True


async def summarize_paper_stage(
    session: AsyncSession,
    *,
    paper_id: UUID,
    paper_version_id: UUID,
    summarizer: SummarizationService,
    body: str | None = None,
) -> PaperSummary:
    """Generate and store one structured summary for an exact revision.

    ``body`` is the parse stage's extracted text; when absent the abstract is
    summarized instead (the parse fallback path). Idempotent on the exact
    (revision, input, provider, model, prompt version) identity.
    """
    paper, version = await _require_paper_version(
        session, paper_id=paper_id, paper_version_id=paper_version_id
    )
    artifacts = ArtifactRepository(session)

    text = body if body is not None and body.strip() else paper.abstract
    input_hash = summary_input_hash(title=paper.title, body=text[: summarizer.max_input_chars])
    existing = await artifacts.find_summary_by_input(
        paper_version_id=version.id,
        input_hash=input_hash,
        prompt_version=SUMMARY_PROMPT_VERSION,
    )
    if existing is not None:
        if existing.source_match_status is SourceMatchStatus.NOT_CHECKED:
            stored_chunks = await artifacts.list_chunks_for_version(paper_version_id=version.id)
            _attach_claim_provenance(existing, cast("Sequence[ChunkSource]", stored_chunks))
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
    stored_chunks = await artifacts.list_chunks_for_version(paper_version_id=version.id)
    _attach_claim_provenance(stored, cast("Sequence[ChunkSource]", stored_chunks))
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
    paper_version_id: UUID,
    sections: list[ParsedSection],
    max_tokens: int,
    overlap_tokens: int,
) -> int:
    """Chunk parsed sections for an exact revision; returns the chunk count.

    Re-running replaces the revision's chunks with identical content (same
    hashes), so downstream embedding stays consistent.
    """
    _, version = await _require_paper_version(
        session, paper_id=paper_id, paper_version_id=paper_version_id
    )
    artifacts = ArtifactRepository(session)

    drafts = chunk_sections(sections, max_tokens=max_tokens, overlap_tokens=overlap_tokens)
    stored = await artifacts.replace_chunks(
        paper_id=paper_id, paper_version_id=version.id, drafts=drafts
    )
    # Replacing chunks invalidates any chunk identities recorded earlier, so
    # claim provenance is recomputed for every summary of this exact revision.
    for summary in await artifacts.list_summaries_for_version(paper_version_id=version.id):
        _attach_claim_provenance(summary, cast("Sequence[ChunkSource]", stored))
    logger.info("chunks_stored", paper_id=str(paper_id), chunks=len(stored))
    return len(stored)


async def embed_chunks_stage(
    session: AsyncSession,
    *,
    paper_id: UUID,
    paper_version_id: UUID,
    embedder: EmbeddingService,
    batch_limit: int = 512,
) -> int:
    """Embed all unembedded chunks of an exact revision; returns the count.

    Only chunks without vectors are fetched, so retries after a partial
    failure resume where the previous attempt stopped.
    """
    _, version = await _require_paper_version(
        session, paper_id=paper_id, paper_version_id=paper_version_id
    )
    artifacts = ArtifactRepository(session)

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

    logger.info("chunks_embedded", paper_id=str(paper_id), chunks=embedded)
    return embedded
