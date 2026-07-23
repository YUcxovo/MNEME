"""CLI contract tests for manual Semantic Scholar graph synchronization."""

import asyncio
import json
from uuid import uuid4

import pytest

from mneme.core.config import Settings
from mneme.repositories.citation_graph import CitationPersistenceResult
from mneme.services.semantic_scholar.sync import (
    SemanticGraphSyncSummary,
    SemanticGraphTargetNotFound,
)
from mneme.tasks import sync_semantic_graph

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


def _summary() -> SemanticGraphSyncSummary:
    return SemanticGraphSyncSummary(
        paper_id=uuid4(),
        arxiv_id="2401.00001",
        semantic_scholar_id="s2-center",
        references=CitationPersistenceResult(3, 2, 1, 0, 0),
        citations=CitationPersistenceResult(4, 3, 1, 1, 0),
    )


def test_parser_requires_exactly_one_target() -> None:
    parser = sync_semantic_graph.build_parser()
    assert parser.parse_args(["--arxiv-id", "2401.00001"]).arxiv_id == "2401.00001"
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args(["--arxiv-id", "2401.00001", "--paper-id", str(uuid4())])


def test_cli_emits_machine_readable_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    summary = _summary()

    async def successful(**kwargs: object) -> SemanticGraphSyncSummary:
        del kwargs
        return summary

    monkeypatch.setattr(sync_semantic_graph, "run", successful)
    monkeypatch.setattr("sys.argv", ["sync_semantic_graph", "--arxiv-id", summary.arxiv_id])

    sync_semantic_graph.main()

    payload = json.loads(capsys.readouterr().out)
    assert payload["paper_id"] == str(summary.paper_id)
    assert payload["references"] == {
        "duplicates": 1,
        "inserted": 2,
        "observed": 3,
        "resolved": 0,
        "skipped_self": 0,
    }
    assert payload["citations"]["resolved"] == 1


def test_cli_uses_stable_expected_and_unexpected_errors(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    async def missing(**kwargs: object) -> SemanticGraphSyncSummary:
        del kwargs
        raise SemanticGraphTargetNotFound("missing local paper")

    monkeypatch.setattr(sync_semantic_graph, "run", missing)
    monkeypatch.setattr("sys.argv", ["sync_semantic_graph", "--arxiv-id", "missing"])
    with pytest.raises(SystemExit) as captured:
        sync_semantic_graph.main()
    assert captured.value.code == 2
    assert json.loads(capsys.readouterr().err)["error"] == "semantic_graph_target_invalid"

    async def unavailable(**kwargs: object) -> SemanticGraphSyncSummary:
        del kwargs
        raise ConnectionError("sensitive database location")

    monkeypatch.setattr(sync_semantic_graph, "run", unavailable)
    with pytest.raises(SystemExit) as captured:
        sync_semantic_graph.main()
    assert captured.value.code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["error"] == "semantic_graph_unavailable"
    assert "sensitive" not in error["message"]


def test_run_rejects_unbounded_limit_before_allocating_resources() -> None:
    settings = Settings(semantic_scholar_max_neighbors=10, _env_file=None)
    with pytest.raises(ValueError, match="maximum"):
        asyncio.run(
            sync_semantic_graph.run(
                settings=settings,
                arxiv_id="2401.00001",
                limit=11,
            )
        )
