"""Execution-path tests for the RAG evaluation CLI."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest

from mneme.ai.evaluation import QAFixture, load_qa_fixtures
from mneme.cli.run_qa_eval import (
    DEFAULT_FIXTURES,
    build_parser,
    build_run_config,
    resolve_runnable,
)
from mneme.core.config import Settings


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


def _settings() -> Settings:
    return Settings(database_url="postgresql+asyncpg://x:x@localhost/x", jwt_secret="s" * 32)


@pytest.mark.base
@pytest.mark.rag
def test_run_config_snapshots_reproducibility_settings() -> None:
    config = build_run_config(_settings(), embedding_model="text-embedding-3-small")

    assert config.llm_provider == "anthropic"
    assert config.llm_model == "claude-opus-4-8"
    assert config.prompt_version == "qa-v2"
    assert config.embedding_backend == "openai"
    assert config.embedding_model == "text-embedding-3-small"
    assert config.retrieval_top_k == 8
    assert config.context_anchor_count == 2
    assert config.rerank_top_n == 4
    assert config.min_evidence_score == 0.25
    assert config.max_output_tokens == 512
    assert config.cache_enabled is True
    assert config.qa_cache_ttl_seconds == 86400


class _ScriptedResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalar_one(self) -> Any:
        return self._value


class _ScriptedSession:
    """AsyncSession stand-in returning pre-scripted query results in order."""

    def __init__(self, results: list[Any]) -> None:
        self._results = list(results)

    async def execute(self, _statement: Any) -> _ScriptedResult:
        return _ScriptedResult(self._results.pop(0))


def _fixture(arxiv_version: int | None = 2) -> QAFixture:
    return QAFixture(
        fixture_id="qa-x",
        arxiv_id="0000.00000",
        arxiv_version=arxiv_version,
        section_hint="Method",
        question="Q?",
        reference_answer="A.",
        expected_keywords=("k",),
    )


def _resolve(session: _ScriptedSession, fixture: QAFixture) -> Any:
    return asyncio.run(
        resolve_runnable(session, fixture, embedding_model="text-embedding-3-small")  # type: ignore[arg-type]
    )


@pytest.mark.base
@pytest.mark.rag
def test_resolve_skips_unpinned_fixture_before_touching_the_database() -> None:
    skip = _resolve(_ScriptedSession([]), _fixture(arxiv_version=None))

    assert skip["reason"] == "fixture_not_version_pinned"


@pytest.mark.base
@pytest.mark.rag
def test_resolve_skips_missing_paper_and_missing_pinned_revision() -> None:
    assert _resolve(_ScriptedSession([None]), _fixture())["reason"] == "paper_not_ingested"

    paper = SimpleNamespace(id=uuid4())
    skip = _resolve(_ScriptedSession([paper, None]), _fixture())
    assert skip["reason"] == "pinned_version_not_ingested"
    assert "0000.00000v2" in skip["detail"]


@pytest.mark.base
@pytest.mark.rag
def test_resolve_requires_a_complete_embedding_set_for_the_configured_model() -> None:
    paper = SimpleNamespace(id=uuid4())
    version = SimpleNamespace(id=uuid4(), version_number=2)

    # 10 chunks, only 7 embedded by the configured model: not runnable.
    skip = _resolve(_ScriptedSession([paper, version, 10, 7]), _fixture())
    assert skip["reason"] == "embeddings_incomplete"
    assert "7/10" in skip["detail"]
    assert "text-embedding-3-small" in skip["detail"]

    # Zero chunks is incomplete too, never runnable.
    assert (
        _resolve(_ScriptedSession([paper, version, 0, 0]), _fixture())["reason"]
        == "embeddings_incomplete"
    )

    # A fully embedded revision resolves to the exact pinned row.
    resolved = _resolve(_ScriptedSession([paper, version, 10, 10]), _fixture())
    assert resolved == (paper, version)
