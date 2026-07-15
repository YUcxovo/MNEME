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


def load_qa_fixtures(path: Path) -> QAFixtureFile:
    """Load and validate a fixture file, failing loudly on schema drift."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    fixture_file = QAFixtureFile.model_validate(payload)
    fixture_ids = [fixture.fixture_id for fixture in fixture_file.fixtures]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError(f"Duplicate fixture_id values in {path}.")
    return fixture_file
