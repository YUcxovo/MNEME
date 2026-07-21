"""Aggregate one revision's artifacts into the public paper processing state."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.models.artifact import PaperChunk, PaperSummary, SummaryStatus
from mneme.models.paper import Paper, PaperVersion, ParseQuality, ProcessingStatus


async def reconcile_processing_status(
    session: AsyncSession, *, paper_id: UUID, paper_version_id: UUID
) -> ProcessingStatus:
    """Mark the latest revision ready only when all required artifacts exist.

    AI stages lock the paper row before writing, so concurrent summary and
    embedding completions serialize and the final finisher observes the other
    stage's committed artifacts.
    """
    paper = await session.get(Paper, paper_id)
    version = await session.get(PaperVersion, paper_version_id)
    if paper is None or version is None or version.paper_id != paper_id:
        raise ValueError("Cannot reconcile an unknown paper revision.")

    latest_version_id = await session.scalar(
        select(PaperVersion.id)
        .where(PaperVersion.paper_id == paper_id)
        .order_by(PaperVersion.version_number.desc())
        .limit(1)
    )
    if latest_version_id != paper_version_id:
        return paper.processing_status
    if version.parsed_checksum is None or version.parse_quality is None:
        return paper.processing_status

    summary = await session.scalar(
        select(PaperSummary)
        .where(PaperSummary.paper_version_id == paper_version_id)
        .order_by(PaperSummary.created_at.desc())
        .limit(1)
    )
    chunk_counts = (
        await session.execute(
            select(
                func.count(PaperChunk.id),
                func.count(PaperChunk.embedding),
            ).where(PaperChunk.paper_version_id == paper_version_id)
        )
    ).one()
    total_chunks = int(chunk_counts[0])
    embedded_chunks = int(chunk_counts[1])

    complete = summary is not None and total_chunks > 0 and embedded_chunks == total_chunks
    full_quality = (
        version.parse_quality is not ParseQuality.ABSTRACT_ONLY
        and summary is not None
        and summary.status is SummaryStatus.READY
    )
    paper.processing_status = (
        ProcessingStatus.READY if complete and full_quality else ProcessingStatus.PARTIAL
    )
    await session.flush()
    return paper.processing_status
