"""Frozen QA fixture format and loader (see docs/architecture/ai-evaluation.md)."""

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class QAFixture(BaseModel):
    """One manually curated question with grading hints.

    ``expected_keywords`` powers the M1 keyword-coverage placeholder metric;
    richer grading (recall@k, source-match rate) lands with real retrieval.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_id: str = Field(min_length=1)
    arxiv_id: str = Field(min_length=1)
    section_hint: str | None = None
    question: str = Field(min_length=1)
    reference_answer: str = Field(min_length=1)
    expected_keywords: tuple[str, ...] = Field(min_length=1)
    must_cite: bool = True


class QAFixtureFile(BaseModel):
    """Versioned envelope around a fixture set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_version: str = Field(min_length=1)
    fixtures: tuple[QAFixture, ...] = Field(min_length=1)


class SummaryFixture(BaseModel):
    """One manually checked summarization case.

    ``abstract`` is the exact input handed to the summarizer so runs are
    reproducible offline; ``expected_keywords`` grades the generated ``tldr``
    and key claims with the same coverage metric as QA fixtures.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_id: str = Field(min_length=1)
    arxiv_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    abstract: str = Field(min_length=1)
    expected_keywords: tuple[str, ...] = Field(min_length=1)


class SummaryFixtureFile(BaseModel):
    """Versioned envelope around a summarization fixture set."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    fixture_version: str = Field(min_length=1)
    fixtures: tuple[SummaryFixture, ...] = Field(min_length=1)


def load_qa_fixtures(path: Path) -> QAFixtureFile:
    """Load and validate a fixture file, failing loudly on schema drift."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixture_file = QAFixtureFile.model_validate(payload)
    _reject_duplicate_ids([fixture.fixture_id for fixture in fixture_file.fixtures], path)
    return fixture_file


def load_summary_fixtures(path: Path) -> SummaryFixtureFile:
    """Load and validate a summarization fixture file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixture_file = SummaryFixtureFile.model_validate(payload)
    _reject_duplicate_ids([fixture.fixture_id for fixture in fixture_file.fixtures], path)
    return fixture_file


def _reject_duplicate_ids(fixture_ids: list[str], path: Path) -> None:
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError(f"Duplicate fixture_id values in {path}.")
