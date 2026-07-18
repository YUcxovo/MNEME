"""Versioned prompt templates for summarization and grounded Q&A.

Bumping a ``*_PROMPT_VERSION`` constant invalidates the corresponding cache
entries implicitly (the version participates in the cache key) and is the
only sanctioned way to change a template's observable behavior.
"""

from mneme.ai.types import AITask, ChatMessage, CompletionRequest

SUMMARY_PROMPT_VERSION = "summary-v1"
QA_PROMPT_VERSION = "qa-v1"

_SUMMARY_SYSTEM = (
    "You are a scientific paper summarizer for a research assistant. "
    "You respond with a single JSON object and nothing else: no prose, no "
    "markdown fences. The JSON object has exactly these keys: "
    '"tldr" (string, at most 3 sentences, plain language), '
    '"key_claims" (array of 2-5 short strings, each one concrete claim or result), '
    '"methodology" (string or null, 1-2 sentences on how the work was done), '
    '"limitations" (string or null, 1-2 sentences on stated limitations). '
    "Only state what the provided text supports; never invent numbers or claims."
)

_QA_SYSTEM = (
    "You answer questions about one scientific paper using only the provided "
    "evidence excerpts. Every claim in your answer must cite its supporting "
    "excerpt with a bracketed number like [1] or [2]. If the evidence does "
    "not contain the answer, reply exactly: INSUFFICIENT_EVIDENCE. "
    "Keep answers under 200 words and do not use outside knowledge."
)


def build_summary_request(*, title: str, body: str, max_output_tokens: int) -> CompletionRequest:
    """Build the structured-summary completion request for one paper."""
    prompt = f"Title: {title}\n\nPaper text:\n{body}\n\nReturn the JSON object now."
    return CompletionRequest(
        task=AITask.SUMMARIZE,
        messages=(ChatMessage(role="user", content=prompt),),
        system=_SUMMARY_SYSTEM,
        max_output_tokens=max_output_tokens,
        prompt_version=SUMMARY_PROMPT_VERSION,
    )


def build_qa_request(
    *, question: str, evidence: list[str], max_output_tokens: int
) -> CompletionRequest:
    """Build the grounded Q&A request with numbered evidence excerpts."""
    blocks = "\n\n".join(f"[{index + 1}] {text}" for index, text in enumerate(evidence))
    prompt = f"Evidence excerpts:\n{blocks}\n\nQuestion: {question}\n\nAnswer with citations:"
    return CompletionRequest(
        task=AITask.QA,
        messages=(ChatMessage(role="user", content=prompt),),
        system=_QA_SYSTEM,
        max_output_tokens=max_output_tokens,
        prompt_version=QA_PROMPT_VERSION,
    )
