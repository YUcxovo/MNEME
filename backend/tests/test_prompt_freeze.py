"""Milestone 5 freeze of the shipped prompt templates and model routing.

The demo Q&A curation and the recorded thesis evaluations are only valid for
the exact templates and default routes they were run against. This module
pins those artifacts: changing a template or a default model makes a test
fail, forcing an explicit version bump (which also invalidates the
completion caches) and a re-validation of the demo set.
"""

import hashlib

import pytest

from mneme.ai import prompts
from mneme.ai.types import AITask
from mneme.core.config import Settings

FROZEN_SUMMARY_VERSION = "summary-v1"
FROZEN_QA_VERSION = "qa-v2"

# SHA-256 of the system templates as validated in the recorded M4 runs and
# curated for the M5 demo. Editing a template must bump its version constant
# and update this pin deliberately, never as a side effect.
FROZEN_SUMMARY_SYSTEM_SHA256 = "5d09d2350a02ceb536b5aea400e60568f1a69ed1edc53d8699cc4a909640b047"
FROZEN_QA_SYSTEM_SHA256 = "04b3ee49eb951bc10f0a928d96bb4b834dfd493209aeb6c30f7a03ce61e16db3"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.base
def test_prompt_versions_are_frozen() -> None:
    assert prompts.SUMMARY_PROMPT_VERSION == FROZEN_SUMMARY_VERSION
    assert prompts.QA_PROMPT_VERSION == FROZEN_QA_VERSION


@pytest.mark.base
def test_summary_template_matches_frozen_hash() -> None:
    assert _sha256(prompts._SUMMARY_SYSTEM) == FROZEN_SUMMARY_SYSTEM_SHA256, (
        "summary system template changed without bumping SUMMARY_PROMPT_VERSION "
        "and re-validating the demo set"
    )


@pytest.mark.base
def test_qa_template_matches_frozen_hash() -> None:
    assert _sha256(prompts._QA_SYSTEM) == FROZEN_QA_SYSTEM_SHA256, (
        "QA system template changed without bumping QA_PROMPT_VERSION "
        "and re-validating the demo set"
    )


@pytest.mark.base
def test_summary_request_construction_is_frozen() -> None:
    request = prompts.build_summary_request(
        title="Frozen Title", body="Frozen body.", max_output_tokens=64
    )
    assert request.task is AITask.SUMMARIZE
    assert request.system == prompts._SUMMARY_SYSTEM
    assert request.prompt_version == FROZEN_SUMMARY_VERSION
    assert request.max_output_tokens == 64
    assert [message.role for message in request.messages] == ["user"]
    assert request.messages[0].content == (
        "Title: Frozen Title\n\nPaper text:\nFrozen body.\n\nReturn the JSON object now."
    ), (
        "summary user-message construction changed without bumping "
        "SUMMARY_PROMPT_VERSION and re-validating the demo set"
    )


@pytest.mark.base
def test_qa_request_construction_is_frozen() -> None:
    request = prompts.build_qa_request(
        question="Frozen question?",
        evidence=["First excerpt.", "Second excerpt."],
        max_output_tokens=64,
    )
    assert request.task is AITask.QA
    assert request.system == prompts._QA_SYSTEM
    assert request.prompt_version == FROZEN_QA_VERSION
    assert request.max_output_tokens == 64
    assert [message.role for message in request.messages] == ["user"]
    assert request.messages[0].content == (
        "Evidence excerpts:\n"
        "[1] First excerpt.\n\n"
        "[2] Second excerpt.\n\n"
        "Question: Frozen question?\n\n"
        "Answer with citations:"
    ), (
        "QA user-message construction changed without bumping "
        "QA_PROMPT_VERSION and re-validating the demo set"
    )


@pytest.mark.base
def test_default_model_routing_is_frozen() -> None:
    settings = Settings(_env_file=None)
    assert settings.llm_qa_model == "claude-opus-4-8", (
        "QA stays on the flagship route: the mid tier failed the refusal-marker "
        "contract (0 of 3) in the recorded tier comparison"
    )
    assert settings.llm_summary_model == "claude-haiku-4-5", (
        "summarization routes to the mid tier per the recorded structural tier "
        "study (7/7 parsed, claim support 0.95 vs 0.94, 6.6x cheaper)"
    )
