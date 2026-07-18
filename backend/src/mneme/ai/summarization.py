"""Structured summary generation and strict-but-forgiving response parsing."""

import hashlib
import json
import re

import structlog
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mneme.ai.prompts import SUMMARY_PROMPT_VERSION, build_summary_request
from mneme.ai.service import LLMService
from mneme.ai.types import AIError, CompletionResult
from mneme.models.artifact import SummaryStatus

logger = structlog.get_logger(__name__)

_CODE_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


class SummaryParseError(AIError):
    """The model response could not be parsed into a structured summary."""


class StructuredSummary(BaseModel):
    """Validated summary content persisted as ``paper_summaries.content``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    tldr: str = Field(min_length=1, max_length=2000)
    key_claims: tuple[str, ...] = ()
    methodology: str | None = None
    limitations: str | None = None


class SummaryGeneration(BaseModel):
    """One finished generation: parsed content plus persistence metadata."""

    model_config = ConfigDict(frozen=True)

    summary: StructuredSummary
    status: SummaryStatus
    input_hash: str
    completion: CompletionResult


def summary_input_hash(*, title: str, body: str) -> str:
    """Deterministic hash of the exact summarized input, for idempotency."""
    canonical = json.dumps(
        {"title": title, "body": body, "prompt_version": SUMMARY_PROMPT_VERSION},
        sort_keys=True,
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def parse_summary_response(text: str) -> StructuredSummary:
    """Parse a model response into a summary, tolerating markdown fences."""
    stripped = _CODE_FENCE.sub("", text.strip()).strip()
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end <= start:
        raise SummaryParseError("Response contains no JSON object.")
    try:
        payload = json.loads(stripped[start : end + 1])
    except json.JSONDecodeError as error:
        raise SummaryParseError(f"Response is not valid JSON: {error}") from error
    try:
        return StructuredSummary.model_validate(payload)
    except ValidationError as error:
        raise SummaryParseError(f"Response JSON violates the summary schema: {error}") from error


def _fallback_summary(raw_text: str, abstract: str) -> StructuredSummary:
    """Derive a usable partial summary when structured parsing fails."""
    source = raw_text.strip() or abstract
    normalized = " ".join(source.split())
    tldr = " ".join(_SENTENCE_BOUNDARY.split(normalized)[:2]).strip() or normalized[:400]
    return StructuredSummary(tldr=tldr)


class SummarizationService:
    """Generate one structured summary per paper revision through LLMService."""

    def __init__(self, llm: LLMService, *, max_input_chars: int, max_output_tokens: int) -> None:
        self._llm = llm
        self._max_input_chars = max_input_chars
        self._max_output_tokens = max_output_tokens

    @property
    def max_input_chars(self) -> int:
        """Input truncation limit; callers use it to precompute input hashes."""
        return self._max_input_chars

    @property
    def max_output_tokens(self) -> int:
        """Generation cap recorded in ``generation_parameters``."""
        return self._max_output_tokens

    async def summarize(self, *, title: str, abstract: str, body: str | None) -> SummaryGeneration:
        """Summarize the best available text (parsed body, else abstract).

        A response that fails structured parsing degrades to a
        ``status=partial`` summary derived from the raw completion instead of
        failing the pipeline stage; the telemetry still records the real cost.
        """
        text = body if body is not None and body.strip() else abstract
        truncated = text[: self._max_input_chars]
        input_hash = summary_input_hash(title=title, body=truncated)
        request = build_summary_request(
            title=title, body=truncated, max_output_tokens=self._max_output_tokens
        )
        completion = await self._llm.complete(request)
        try:
            summary = parse_summary_response(completion.text)
            status = SummaryStatus.READY if body else SummaryStatus.PARTIAL
        except SummaryParseError as error:
            logger.warning("summary_parse_failed", input_hash=input_hash, error=str(error))
            summary = _fallback_summary(completion.text, abstract)
            status = SummaryStatus.PARTIAL
        return SummaryGeneration(
            summary=summary,
            status=status,
            input_hash=input_hash,
            completion=completion,
        )
