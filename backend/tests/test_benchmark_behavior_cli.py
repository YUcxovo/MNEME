"""CLI contracts for the retained behavior performance benchmark."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mneme.cli import benchmark_behavior
from mneme.evaluation.behavior.performance_models import (
    BehaviorPerformanceConfig,
    PerformanceScale,
)
from mneme.evaluation.behavior.provenance import SourceIdentity

pytestmark = pytest.mark.base


def _tiny_config() -> BehaviorPerformanceConfig:
    return BehaviorPerformanceConfig(
        embedding_dimensions=8,
        warmup_repetitions=1,
        measured_repetitions=2,
        top_k=2,
        scales=(PerformanceScale("tiny", 12, 3, 5),),
    )


def test_parser_requires_an_explicit_output() -> None:
    with pytest.raises(SystemExit):
        benchmark_behavior.build_parser().parse_args([])

    arguments = benchmark_behavior.build_parser().parse_args(
        ["--output", "/tmp/performance.json", "--require-clean"]
    )
    assert arguments.output == Path("/tmp/performance.json")
    assert arguments.require_clean is True


def test_run_writes_sanitized_artifact_with_raw_samples(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = SourceIdentity(revision="a" * 40, branch="test", dirty=False)
    monkeypatch.setattr(benchmark_behavior, "collect_source_identity", lambda _: source)
    output = tmp_path / "private" / "performance.json"

    result = benchmark_behavior.run(
        output_path=output,
        require_clean=True,
        config=_tiny_config(),
        repo_root=tmp_path,
        measured_at=datetime(2026, 7, 27, 13, tzinfo=UTC),
    )

    assert result == benchmark_behavior.BenchmarkRunResult(
        case_count=1,
        output="private/performance.json",
        repetitions=2,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "behavior-performance-artifact-v1"
    assert payload["measured_at_utc"] == "2026-07-27T13:00:00Z"
    assert payload["source"] == source.model_dump(mode="json")
    assert payload["command"][-1] == "--require-clean"
    assert len(payload["benchmark"]["cases"][0]["aggregation"]["samples_ms"]) == 2
    assert str(tmp_path) not in json.dumps(payload)


def test_dirty_tree_fails_before_benchmark_or_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        benchmark_behavior,
        "collect_source_identity",
        lambda _: SourceIdentity(revision="b" * 40, branch="test", dirty=True),
    )

    with pytest.raises(benchmark_behavior.BehaviorBenchmarkWorktreeDirtyError):
        benchmark_behavior.run(
            output_path=tmp_path / "performance.json",
            require_clean=True,
            config=_tiny_config(),
            repo_root=tmp_path,
        )

    assert not (tmp_path / "performance.json").exists()


def test_cli_success_and_errors_use_stable_safe_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = benchmark_behavior.BenchmarkRunResult(
        case_count=3,
        output="performance.json",
        repetitions=30,
    )
    monkeypatch.setattr(benchmark_behavior, "run", lambda **_: result)
    monkeypatch.setattr("sys.argv", ["benchmark_behavior", "--output", "/tmp/result.json"])

    benchmark_behavior.main()

    assert json.loads(capsys.readouterr().out) == {
        "cases": 3,
        "output": "performance.json",
        "repetitions": 30,
        "status": "ok",
    }


@pytest.mark.parametrize(
    ("error", "exit_code", "code"),
    [
        (
            benchmark_behavior.BehaviorBenchmarkWorktreeDirtyError(),
            2,
            "behavior_benchmark_worktree_dirty",
        ),
        (ValueError("private detail"), 2, "behavior_benchmark_input_invalid"),
        (RuntimeError("private detail"), 1, "behavior_benchmark_unavailable"),
    ],
)
def test_cli_errors_do_not_disclose_internal_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    exit_code: int,
    code: str,
) -> None:
    def fail(**kwargs: object) -> None:
        del kwargs
        raise error

    monkeypatch.setattr(benchmark_behavior, "run", fail)
    monkeypatch.setattr("sys.argv", ["benchmark_behavior", "--output", "/tmp/result.json"])

    with pytest.raises(SystemExit) as captured:
        benchmark_behavior.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == exit_code
    assert payload == {"error": code, "status": "error"}
    assert "private" not in json.dumps(payload)
