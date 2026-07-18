"""Summarization evaluation seed: loading and grading integration."""

import json
from pathlib import Path

import pytest

from mneme.ai.evaluation.fixtures import load_summary_fixtures
from mneme.ai.evaluation.harness import keyword_coverage
from mneme.ai.summarization import parse_summary_response

SEED_PATH = Path(__file__).parent / "fixtures" / "eval" / "summary_seed_v1.json"


@pytest.mark.base
@pytest.mark.rag
def test_summary_seed_loads_with_five_unique_cases() -> None:
    fixture_file = load_summary_fixtures(SEED_PATH)

    assert fixture_file.fixture_version == "summary-seed-v1"
    assert len(fixture_file.fixtures) == 5
    ids = {fixture.fixture_id for fixture in fixture_file.fixtures}
    assert len(ids) == 5


@pytest.mark.base
@pytest.mark.rag
def test_seed_abstracts_contain_their_expected_keywords() -> None:
    fixture_file = load_summary_fixtures(SEED_PATH)

    for fixture in fixture_file.fixtures:
        haystack = f"{fixture.title} {fixture.abstract}".casefold()
        missing = [
            keyword
            for keyword in fixture.expected_keywords
            if keyword.casefold() not in haystack
        ]
        assert not missing, f"{fixture.fixture_id} missing {missing}"


@pytest.mark.base
@pytest.mark.rag
def test_seed_grades_a_structured_summary_with_keyword_coverage() -> None:
    fixture = load_summary_fixtures(SEED_PATH).fixtures[0]
    generated = json.dumps(
        {
            "tldr": "The Transformer replaces recurrence with attention.",
            "key_claims": ["Attention-only models train faster."],
            "methodology": None,
            "limitations": None,
        }
    )

    summary = parse_summary_response(generated)
    graded_text = " ".join([summary.tldr, *summary.key_claims])
    coverage = keyword_coverage(graded_text, fixture.expected_keywords)

    assert coverage >= 2 / 3


@pytest.mark.base
def test_duplicate_fixture_ids_are_rejected(tmp_path: Path) -> None:
    fixture = {
        "fixture_id": "dup",
        "arxiv_id": "1",
        "title": "T",
        "abstract": "A",
        "expected_keywords": ["a"],
    }
    payload = {"fixture_version": "v", "fixtures": [fixture, fixture]}
    path = tmp_path / "dup.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate fixture_id"):
        load_summary_fixtures(path)

