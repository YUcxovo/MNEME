"""Revision-safety tests for persisted AI artifacts."""

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.chunking import ChunkDraft
from mneme.models.artifact import PaperChunk
from mneme.repositories.artifacts import ArtifactRepository


def _draft(*, content: str = "same content") -> ChunkDraft:
    return ChunkDraft(
        chunk_index=0,
        section_title="Introduction",
        content=content,
        content_hash=("a" if content == "same content" else "b") * 64,
        token_count=2,
        page_start=1,
        page_end=1,
    )


def _stored_chunk(*, paper_id, paper_version_id) -> PaperChunk:
    return PaperChunk(
        id=uuid4(),
        paper_id=paper_id,
        paper_version_id=paper_version_id,
        section_title="Introduction",
        chunk_index=0,
        page_start=1,
        page_end=1,
        content="same content",
        content_hash="a" * 64,
        token_count=2,
        embedding=[0.1] * 1536,
        embedding_model="text-embedding-3-small",
    )


def _session_with_chunks(chunks: list[PaperChunk]) -> AsyncMock:
    session = AsyncMock(spec=AsyncSession)
    scalars = MagicMock()
    scalars.all.return_value = chunks
    session.scalars.return_value = scalars
    return session


@pytest.mark.base
@pytest.mark.rag
def test_unchanged_chunk_manifest_preserves_rows_and_embeddings() -> None:
    paper_id = uuid4()
    version_id = uuid4()
    stored = _stored_chunk(paper_id=paper_id, paper_version_id=version_id)
    session = _session_with_chunks([stored])

    result = asyncio.run(
        ArtifactRepository(session).replace_chunks(
            paper_id=paper_id,
            paper_version_id=version_id,
            drafts=[_draft()],
        )
    )

    assert result == [stored]
    assert result[0].embedding is not None
    session.execute.assert_not_awaited()
    session.add_all.assert_not_called()
    session.flush.assert_not_awaited()


@pytest.mark.base
@pytest.mark.rag
def test_changed_chunk_manifest_replaces_revision_rows() -> None:
    paper_id = uuid4()
    version_id = uuid4()
    stored = _stored_chunk(paper_id=paper_id, paper_version_id=version_id)
    session = _session_with_chunks([stored])

    result = asyncio.run(
        ArtifactRepository(session).replace_chunks(
            paper_id=paper_id,
            paper_version_id=version_id,
            drafts=[_draft(content="changed content")],
        )
    )

    assert len(result) == 1
    assert result[0].content == "changed content"
    assert result[0].embedding is None
    delete_statement = session.execute.await_args.args[0]
    compiled = delete_statement.compile(dialect=postgresql.dialect())
    assert paper_id in compiled.params.values()
    assert version_id in compiled.params.values()
    session.add_all.assert_called_once()
    session.flush.assert_awaited_once()


@pytest.mark.base
@pytest.mark.rag
def test_summary_and_search_queries_are_revision_scoped() -> None:
    paper_id = uuid4()
    version_id = uuid4()
    session = AsyncMock(spec=AsyncSession)
    rows = MagicMock()
    rows.all.return_value = []
    session.execute.return_value = rows
    repository = ArtifactRepository(session)

    asyncio.run(repository.get_summary_for_version(version_id))
    summary_statement = session.scalar.await_args.args[0]
    summary_query = summary_statement.compile(dialect=postgresql.dialect())
    assert version_id in summary_query.params.values()
    assert "paper_summaries.paper_version_id" in str(summary_query)

    asyncio.run(
        repository.search_chunks(
            paper_id=paper_id,
            paper_version_id=version_id,
            query_embedding=(0.1,) * 1536,
            limit=3,
        )
    )
    search_statement = session.execute.await_args.args[0]
    search_query = search_statement.compile(dialect=postgresql.dialect())
    assert paper_id in search_query.params.values()
    assert version_id in search_query.params.values()
    assert "paper_chunks.paper_version_id" in str(search_query)
