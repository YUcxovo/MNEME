"""Argument contract for the RAG evaluation CLI."""

from pathlib import Path

import pytest

from mneme.ai.evaluation import load_qa_fixtures
from mneme.cli.run_qa_eval import DEFAULT_FIXTURES, build_parser


@pytest.mark.base
@pytest.mark.rag
def test_default_fixture_path_points_at_current_seed() -> None:
    assert DEFAULT_FIXTURES.is_file()
    assert load_qa_fixtures(DEFAULT_FIXTURES).fixture_version == "qa-seed-v2"


@pytest.mark.base
@pytest.mark.rag
def test_parser_accepts_fixture_and_output_overrides(tmp_path: Path) -> None:
    parser = build_parser()

    defaults = parser.parse_args([])
    assert defaults.fixtures == DEFAULT_FIXTURES
    assert defaults.output is None

    override = parser.parse_args(
        ["--fixtures", str(tmp_path / "f.json"), "--output", str(tmp_path / "out.json")]
    )
    assert override.fixtures == tmp_path / "f.json"
    assert override.output == tmp_path / "out.json"
