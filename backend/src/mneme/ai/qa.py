"""Grounded single-paper Q&A: rerank, generate from evidence, verify citations.

The reranker is an honest lexical blend, not a cross-encoder: retrieval
scores come from vector similarity and are combined with content-word
overlap between question and chunk. Citation verification checks that every
cited excerpt exists and that the answer shares enough content words with
its cited evidence to count as source-matched.
"""

import re

import structlog
from pydantic import BaseModel, ConfigDict, Field

from mneme.ai.prompts import build_qa_request
from mneme.ai.retrieval import RetrievedChunk
from mneme.ai.service import LLMService
from mneme.ai.types import CompletionResult
from mneme.models.qa import QaSourceMatchStatus

logger = structlog.get_logger(__name__)

REFUSAL_ANSWER = "The paper does not contain enough evidence to answer this question."
_INSUFFICIENT_MARKER = "INSUFFICIENT_EVIDENCE"

_WORD = re.compile(r"[a-z0-9]+")
_CITATION = re.compile(r"\[(\d+)\]")
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "for",
        "from",
        "has",
        "have",
        "how",
        "in",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "we",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "does",
        "do",
        "did",
        "not",
        "their",
        "there",
        "these",
        "those",
        "than",
        "then",
        "can",
        "could",
        "should",
        "would",
        "about",
    ]
)

_VECTOR_WEIGHT = 0.7
_LEXICAL_WEIGHT = 0.3
_SOURCE_MATCH_MIN_OVERLAP = 0.3


def content_words(text: str) -> set[str]:
    """Lowercased alphanumeric tokens minus stopwords."""
    return {word for word in _WORD.findall(text.casefold()) if word not in _STOPWORDS}


def lexical_overlap(question: str, text: str) -> float:
    """Fraction of the question's content words present in the text."""
    question_words = content_words(question)
    if not question_words:
        return 0.0
    return len(question_words & content_words(text)) / len(question_words)


def rerank(question: str, chunks: list[RetrievedChunk], *, top_n: int) -> list[RetrievedChunk]:
    """Blend vector similarity with lexical overlap and keep the best chunks.

    Ties break on the original retrieval order (chunk order in ``chunks``),
    so reranking is deterministic for identical inputs.
    """
    scored = [
        (
            chunk.model_copy(
                update={
                    "score": round(
                        _VECTOR_WEIGHT * chunk.score
                        + _LEXICAL_WEIGHT * lexical_overlap(question, chunk.content),
                        6,
                    )
                }
            ),
            position,
        )
        for position, chunk in enumerate(chunks)
    ]
    scored.sort(key=lambda item: (-item[0].score, item[1]))
    return [chunk for chunk, _ in scored[:top_n]]


class AnswerCitation(BaseModel):
    """One verified citation pointing at a stored chunk."""

    model_config = ConfigDict(frozen=True)

    chunk: RetrievedChunk
    marker: int = Field(ge=1)
    source_match: bool


class GroundedAnswer(BaseModel):
    """The final grounded answer with verification results and telemetry."""

    model_config = ConfigDict(frozen=True)

    answer: str
    citations: tuple[AnswerCitation, ...]
    source_match_status: QaSourceMatchStatus
    completion: CompletionResult | None = None


def verify_citations(
    answer: str, evidence: list[RetrievedChunk]
) -> tuple[tuple[AnswerCitation, ...], QaSourceMatchStatus]:
    """Validate citation markers against evidence and check answer grounding.

    A citation is source-matched when enough of the answer's content words
    appear in the cited chunk. Markers pointing outside the evidence list are
    dropped rather than fabricated into citations.
    """
    markers = {int(match) for match in _CITATION.findall(answer)}
    valid_markers = sorted(marker for marker in markers if 1 <= marker <= len(evidence))
    if not valid_markers:
        return (), QaSourceMatchStatus.INSUFFICIENT_EVIDENCE

    answer_words = content_words(_CITATION.sub("", answer))
    citations: list[AnswerCitation] = []
    for marker in valid_markers:
        chunk = evidence[marker - 1]
        chunk_words = content_words(chunk.content)
        overlap = len(answer_words & chunk_words) / len(answer_words) if answer_words else 0.0
        citations.append(
            AnswerCitation(
                chunk=chunk,
                marker=marker,
                source_match=overlap >= _SOURCE_MATCH_MIN_OVERLAP,
            )
        )

    matched = sum(1 for citation in citations if citation.source_match)
    if matched == len(citations):
        status = QaSourceMatchStatus.MATCHED
    elif matched > 0:
        status = QaSourceMatchStatus.PARTIAL
    else:
        status = QaSourceMatchStatus.INSUFFICIENT_EVIDENCE
    return tuple(citations), status


class GroundedAnswerService:
    """Generate a citation-verified answer from reranked evidence."""

    def __init__(
        self,
        llm: LLMService,
        *,
        rerank_top_n: int,
        min_evidence_score: float,
        max_output_tokens: int,
    ) -> None:
        self._llm = llm
        self._rerank_top_n = rerank_top_n
        self._min_evidence_score = min_evidence_score
        self._max_output_tokens = max_output_tokens

    async def answer(self, *, question: str, chunks: list[RetrievedChunk]) -> GroundedAnswer:
        """Answer from retrieved chunks, refusing when evidence is too weak."""
        evidence = rerank(question, chunks, top_n=self._rerank_top_n)
        if not evidence or evidence[0].score < self._min_evidence_score:
            logger.info(
                "qa_refused_weak_evidence",
                chunks=len(evidence),
                top_score=evidence[0].score if evidence else None,
            )
            return GroundedAnswer(
                answer=REFUSAL_ANSWER,
                citations=(),
                source_match_status=QaSourceMatchStatus.INSUFFICIENT_EVIDENCE,
            )

        request = build_qa_request(
            question=question,
            evidence=[chunk.content for chunk in evidence],
            max_output_tokens=self._max_output_tokens,
        )
        completion = await self._llm.complete(request)
        text = completion.text.strip()
        if not text or _INSUFFICIENT_MARKER in text:
            return GroundedAnswer(
                answer=REFUSAL_ANSWER,
                citations=(),
                source_match_status=QaSourceMatchStatus.INSUFFICIENT_EVIDENCE,
                completion=completion,
            )

        citations, status = verify_citations(text, evidence)
        logger.info(
            "qa_answer_generated",
            citations=len(citations),
            source_match_status=status.value,
            cached=completion.cached,
        )
        return GroundedAnswer(
            answer=text,
            citations=citations,
            source_match_status=status,
            completion=completion,
        )
