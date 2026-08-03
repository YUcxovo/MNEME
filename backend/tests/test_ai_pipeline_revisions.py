"""Exact-revision behavior of the AI pipeline stages."""

import asyncio
from typing import Any, ClassVar
from uuid import UUID, uuid4

import pytest

import mneme.ai.pipeline as pipeline_module
from mneme.ai.pipeline import PaperNotReadyError, chunk_paper_stage, embed_chunks_stage
from mneme.models.artifact import PaperChunk
from mneme.models.paper import Paper, PaperVersion, ProcessingStatus
from mneme.services.documents import ParsedSection


def _paper(paper_id: UUID) -> Paper:
    return Paper(
        id=paper_id,
        arxiv_id=f"revision-test.{paper_id.hex}",
        title="Revision safety",
        abstract="An abstract.",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/revision-test",
        processing_status=ProcessingStatus.PROCESSING,
    )


class FakeSession:
    """Minimal identity-map stand-in used by exact-revision validation."""

    def __init__(self, paper: Paper, version: PaperVersion) -> None:
        self.paper = paper
        self.version = version

    async def get(self, model: type[Any], identity: UUID, **kwargs: object) -> Any | None:
        del kwargs
        if model is Paper and self.paper.id == identity:
            return self.paper
        if model is PaperVersion and self.version.id == identity:
            return self.version
        return None


class FakeArtifacts:
    """Record revision IDs passed from stages into persistence."""

    instances: ClassVar[list["FakeArtifacts"]] = []

    def __init__(self, session: object) -> None:
        self.replaced_version_id: UUID | None = None
        self.embedding_version_ids: list[UUID] = []
        self.embedding_updates: list[object] = []
        self._embedding_batches: list[list[PaperChunk]] = []
        self.instances.append(self)

    async def replace_chunks(self, *, paper_id: UUID, paper_version_id: UUID, drafts):
        self.replaced_version_id = paper_version_id
        return drafts

    async def list_chunks_without_embedding(
        self, *, paper_version_id: UUID, limit: int
    ) -> list[PaperChunk]:
        self.embedding_version_ids.append(paper_version_id)
        return self._embedding_batches.pop(0) if self._embedding_batches else []

    async def set_chunk_embeddings(self, updates: list[object]) -> None:
        self.embedding_updates.extend(updates)

    async def list_summaries_for_version(self, *, paper_version_id: UUID) -> list[object]:
        del paper_version_id
        return []

    async def list_chunks_for_version(self, *, paper_version_id: UUID) -> list[PaperChunk]:
        del paper_version_id
        return []


class FakeEmbedder:
    model = "test-embedding"

    async def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [(0.1, 0.2) for _ in texts]


@pytest.mark.base
@pytest.mark.pipeline
def test_chunk_stage_rejects_revision_owned_by_another_paper(monkeypatch) -> None:
    paper_id = uuid4()
    other_paper_id = uuid4()
    version_id = uuid4()
    session = FakeSession(
        _paper(paper_id),
        PaperVersion(id=version_id, paper_id=other_paper_id, version_number=1),
    )
    monkeypatch.setattr(pipeline_module, "ArtifactRepository", FakeArtifacts)

    with pytest.raises(PaperNotReadyError, match="does not belong"):
        asyncio.run(
            chunk_paper_stage(
                session,  # type: ignore[arg-type]
                paper_id=paper_id,
                paper_version_id=version_id,
                sections=[ParsedSection(title="Intro", text="Some text.")],
                max_tokens=100,
                overlap_tokens=10,
            )
        )


@pytest.mark.base
@pytest.mark.pipeline
def test_chunk_stage_persists_the_requested_revision(monkeypatch) -> None:
    paper_id = uuid4()
    version_id = uuid4()
    session = FakeSession(
        _paper(paper_id),
        PaperVersion(id=version_id, paper_id=paper_id, version_number=1),
    )
    FakeArtifacts.instances.clear()
    monkeypatch.setattr(pipeline_module, "ArtifactRepository", FakeArtifacts)

    count = asyncio.run(
        chunk_paper_stage(
            session,  # type: ignore[arg-type]
            paper_id=paper_id,
            paper_version_id=version_id,
            sections=[ParsedSection(title="Intro", text="Some text.")],
            max_tokens=100,
            overlap_tokens=10,
        )
    )

    assert count == 1
    assert FakeArtifacts.instances[-1].replaced_version_id == version_id


@pytest.mark.base
@pytest.mark.pipeline
def test_embedding_stage_does_not_mark_paper_ready(monkeypatch) -> None:
    paper_id = uuid4()
    version_id = uuid4()
    paper = _paper(paper_id)
    session = FakeSession(
        paper,
        PaperVersion(id=version_id, paper_id=paper_id, version_number=1),
    )
    chunk = PaperChunk(
        id=uuid4(),
        paper_id=paper_id,
        paper_version_id=version_id,
        chunk_index=0,
        content="Some text.",
        content_hash="a" * 64,
    )

    class ArtifactsWithChunk(FakeArtifacts):
        def __init__(self, session: object) -> None:
            super().__init__(session)
            self._embedding_batches = [[chunk], []]

    FakeArtifacts.instances.clear()
    monkeypatch.setattr(pipeline_module, "ArtifactRepository", ArtifactsWithChunk)

    embedded = asyncio.run(
        embed_chunks_stage(
            session,  # type: ignore[arg-type]
            paper_id=paper_id,
            paper_version_id=version_id,
            embedder=FakeEmbedder(),  # type: ignore[arg-type]
        )
    )

    assert embedded == 1
    assert paper.processing_status is ProcessingStatus.PROCESSING
    artifacts = FakeArtifacts.instances[-1]
    assert artifacts.embedding_version_ids == [version_id, version_id]
    assert len(artifacts.embedding_updates) == 1
