"""Aggregate readiness rules for the latest parsed paper revision."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest

from mneme.models.artifact import PaperSummary, SourceMatchStatus, SummaryStatus
from mneme.models.paper import Paper, PaperVersion, ParseQuality, ProcessingStatus
from mneme.services.processing_status import reconcile_processing_status

PAPER_ID = UUID("00000000-0000-0000-0000-000000000111")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000222")
NOW = datetime(2026, 7, 21, tzinfo=UTC)


def _paper() -> Paper:
    return Paper(
        id=PAPER_ID,
        arxiv_id="2607.00001",
        title="Readiness",
        abstract="Abstract",
        primary_category="cs.AI",
        categories=["cs.AI"],
        pdf_url="https://arxiv.org/pdf/2607.00001",
        processing_status=ProcessingStatus.PROCESSING,
        published_at=NOW,
        source_updated_at=NOW,
    )


def _version(quality: ParseQuality) -> PaperVersion:
    return PaperVersion(
        id=VERSION_ID,
        paper_id=PAPER_ID,
        version_number=1,
        source_checksum="a" * 64,
        source_size_bytes=100,
        downloaded_at=NOW,
        parsed_checksum="b" * 64,
        parser_version="parser-v1",
        parse_quality=quality,
        parsed_at=NOW,
    )


def _summary(status: SummaryStatus) -> PaperSummary:
    return PaperSummary(
        id=uuid4(),
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        status=status,
        source_match_status=SourceMatchStatus.NOT_CHECKED,
        content={"tldr": "Summary"},
        provider="fake",
        model_snapshot="fake-v1",
        prompt_version="summary-v1",
        input_hash="c" * 64,
    )


class FakeSession:
    """Return deterministic aggregate rows without a database."""

    def __init__(
        self,
        *,
        paper: Paper,
        version: PaperVersion,
        latest_version_id: UUID,
        summary: PaperSummary | None,
        counts: tuple[int, int],
    ) -> None:
        self.paper = paper
        self.version = version
        self.scalar_values = [latest_version_id, summary]
        self.counts = counts
        self.flushes = 0

    async def get(self, model: type[Any], identity: UUID) -> Any | None:
        if model is Paper and identity == self.paper.id:
            return self.paper
        if model is PaperVersion and identity == self.version.id:
            return self.version
        return None

    async def scalar(self, statement: object) -> object:
        del statement
        return self.scalar_values.pop(0)

    async def execute(self, statement: object) -> SimpleNamespace:
        del statement
        return SimpleNamespace(one=lambda: self.counts)

    async def flush(self) -> None:
        self.flushes += 1


def _reconcile(
    *, quality: ParseQuality, summary_status: SummaryStatus | None, counts: tuple[int, int]
) -> tuple[ProcessingStatus, FakeSession]:
    paper = _paper()
    session = FakeSession(
        paper=paper,
        version=_version(quality),
        latest_version_id=VERSION_ID,
        summary=_summary(summary_status) if summary_status is not None else None,
        counts=counts,
    )
    status = asyncio.run(
        reconcile_processing_status(
            session,  # type: ignore[arg-type]
            paper_id=PAPER_ID,
            paper_version_id=VERSION_ID,
        )
    )
    return status, session


@pytest.mark.base
@pytest.mark.pipeline
def test_structured_summary_and_fully_embedded_chunks_become_ready() -> None:
    status, session = _reconcile(
        quality=ParseQuality.STRUCTURED,
        summary_status=SummaryStatus.READY,
        counts=(3, 3),
    )

    assert status is ProcessingStatus.READY
    assert session.paper.processing_status is ProcessingStatus.READY
    assert session.flushes == 1


@pytest.mark.base
@pytest.mark.pipeline
def test_complete_degraded_artifacts_become_terminal_partial() -> None:
    status, session = _reconcile(
        quality=ParseQuality.ABSTRACT_ONLY,
        summary_status=SummaryStatus.PARTIAL,
        counts=(1, 1),
    )

    assert status is ProcessingStatus.PARTIAL
    assert session.paper.processing_status is ProcessingStatus.PARTIAL


@pytest.mark.base
@pytest.mark.pipeline
@pytest.mark.parametrize(
    ("quality", "summary_status", "counts"),
    [
        (ParseQuality.TEXT_ONLY, SummaryStatus.READY, (2, 1)),
        (ParseQuality.TEXT_ONLY, None, (2, 2)),
    ],
)
def test_incomplete_artifacts_remain_transient_processing(
    quality: ParseQuality,
    summary_status: SummaryStatus | None,
    counts: tuple[int, int],
) -> None:
    status, _ = _reconcile(
        quality=quality,
        summary_status=summary_status,
        counts=counts,
    )

    assert status is ProcessingStatus.PROCESSING


@pytest.mark.base
@pytest.mark.pipeline
def test_stale_revision_cannot_overwrite_current_paper_status() -> None:
    paper = _paper()
    current_version_id = uuid4()
    session = FakeSession(
        paper=paper,
        version=_version(ParseQuality.STRUCTURED),
        latest_version_id=current_version_id,
        summary=_summary(SummaryStatus.READY),
        counts=(1, 1),
    )

    status = asyncio.run(
        reconcile_processing_status(
            session,  # type: ignore[arg-type]
            paper_id=PAPER_ID,
            paper_version_id=VERSION_ID,
        )
    )

    assert status is ProcessingStatus.PROCESSING
    assert paper.processing_status is ProcessingStatus.PROCESSING
    assert session.flushes == 0
