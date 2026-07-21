"""Network-free providers used by the PostgreSQL pipeline integration test."""

import hashlib
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from mneme.ai.prompts import SUMMARY_PROMPT_VERSION
from mneme.ai.summarization import (
    StructuredSummary,
    SummaryGeneration,
    summary_input_hash,
)
from mneme.ai.types import AITask, CompletionResult, ProviderName, TokenUsage
from mneme.models.artifact import SummaryStatus
from mneme.models.paper import ParseQuality
from mneme.services.documents import (
    ParsedDocument,
    ParsedSection,
    PdfDownloadResult,
)

SOURCE_PDF = b"%PDF-1.7\nMneme deterministic integration fixture\n%%EOF\n"


class RecordingQueue:
    """Record ARQ-compatible calls so the test can drive workers explicitly."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> object:
        self.calls.append((function, args, kwargs))
        return SimpleNamespace()

    def pop(self, function: str) -> tuple[tuple[object, ...], dict[str, object]]:
        for index, (candidate, args, kwargs) in enumerate(self.calls):
            if candidate == function:
                self.calls.pop(index)
                return args, kwargs
        raise AssertionError(f"No queued {function} job")


class FixtureDownloader:
    """Install deterministic source bytes without network access."""

    async def download(
        self,
        *,
        url: str,
        destination: Path,
        expected_checksum: str | None,
    ) -> PdfDownloadResult:
        assert url.endswith("v1")
        checksum = hashlib.sha256(SOURCE_PDF).hexdigest()
        assert expected_checksum in (None, checksum)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(SOURCE_PDF)
        return PdfDownloadResult(destination, checksum, len(SOURCE_PDF), reused=False)


class FixtureParser:
    """Produce a structured exact-revision sidecar from the fixture PDF."""

    parser_version = "e2e-parser-v1"

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
        assert source_path.read_bytes() == SOURCE_PDF
        assert abstract
        return ParsedDocument(
            parser_version=self.parser_version,
            paper_id=paper_id,
            paper_version_id=paper_version_id,
            source_checksum=source_checksum,
            parse_quality=ParseQuality.STRUCTURED,
            page_count=1,
            sections=[
                ParsedSection(
                    title="Introduction",
                    text="This paper presents a deterministic research pipeline.",
                    page_start=1,
                    page_end=1,
                ),
                ParsedSection(
                    title="Results",
                    text="The staged pipeline preserves revision identity and provenance.",
                    page_start=1,
                    page_end=1,
                ),
            ],
            parsed_at=parsed_at,
        )


class FixtureSummarizer:
    """Return a provider-shaped structured result without making an LLM call."""

    max_input_chars = 10_000
    max_output_tokens = 256

    async def summarize(self, *, title: str, abstract: str, body: str | None) -> SummaryGeneration:
        assert title and abstract and body
        input_hash = summary_input_hash(title=title, body=body[: self.max_input_chars])
        completion = CompletionResult(
            text="fixture",
            task=AITask.SUMMARIZE,
            provider=ProviderName.ANTHROPIC,
            model="fixture-summary-v1",
            prompt_version=SUMMARY_PROMPT_VERSION,
            usage=TokenUsage(input_tokens=20, output_tokens=10),
            estimated_cost=Decimal("0"),
            latency_ms=1,
            cached=False,
        )
        return SummaryGeneration(
            summary=StructuredSummary(
                tldr="A revision-safe deterministic research pipeline.",
                key_claims=("Pipeline stages preserve exact revision identity.",),
                methodology="Durable staged jobs with provenance.",
                limitations="Synthetic integration fixture.",
            ),
            status=SummaryStatus.READY,
            input_hash=input_hash,
            completion=completion,
        )


class FixtureEmbedder:
    """Return pgvector-compatible deterministic vectors."""

    model = "fixture-embedding-v1"

    async def embed_texts(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [tuple([float(index + 1) / 10] + [0.0] * 1535) for index, _ in enumerate(texts)]
