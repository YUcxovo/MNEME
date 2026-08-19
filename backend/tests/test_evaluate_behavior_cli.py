"""CLI contract tests for controlled offline behavior evaluation."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mneme.cli import evaluate_behavior
from mneme.evaluation.behavior.provenance import SourceIdentity

FIXTURE_PATH = evaluate_behavior.DEFAULT_FIXTURE


@pytest.mark.base
def test_parser_defaults_to_the_versioned_fixture_and_requires_an_explicit_mode() -> None:
    arguments = evaluate_behavior.build_parser().parse_args([])

    assert arguments.fixture == FIXTURE_PATH
    assert arguments.output is None
    assert arguments.recorded is False
    with pytest.raises(evaluate_behavior.BehaviorEvaluationInputError, match="requires"):
        evaluate_behavior.run(
            fixture_path=FIXTURE_PATH,
            output_dir=None,
            recorded=False,
        )


@pytest.mark.base
def test_exploratory_run_writes_complete_artifacts_only_to_requested_directory(
    tmp_path: Path,
) -> None:
    output = tmp_path / "behavior-exploratory"

    result = evaluate_behavior.run(
        fixture_path=FIXTURE_PATH,
        output_dir=output,
        recorded=False,
        measured_at=datetime(2026, 7, 27, 12, 0, tzinfo=UTC),
    )

    assert result == evaluate_behavior.EvaluationRunResult(
        case_count=108,
        fixture_version="behavior-controlled-v1",
        model_count=9,
        output="behavior-exploratory",
        recorded=False,
    )
    expected = {
        "raw/case_results.jsonl",
        "raw/environment.json",
        "raw/run_manifest.json",
        "summary.csv",
        "summary.json",
    }
    assert {
        path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()
    } == expected
    manifest = json.loads((output / "raw/run_manifest.json").read_text())
    summary = json.loads((output / "summary.json").read_text())
    assert manifest["recorded"] is False
    assert manifest["controlled_synthetic"] is True
    assert manifest["measured_at_utc"] == "2026-07-27T12:00:00Z"
    assert str(tmp_path) not in json.dumps(manifest)
    assert summary["invariant_failures"] == []
    assert len((output / "raw/case_results.jsonl").read_text().splitlines()) == 108


@pytest.mark.base
def test_recorded_dirty_tree_fails_before_any_destination_is_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        evaluate_behavior,
        "collect_source_identity",
        lambda _: SourceIdentity(revision="a" * 40, branch="test", dirty=True),
    )

    with pytest.raises(evaluate_behavior.BehaviorEvaluationWorktreeDirtyError):
        evaluate_behavior.run(
            fixture_path=tmp_path / "missing.json",
            output_dir=None,
            recorded=True,
            repo_root=tmp_path,
        )

    assert not (tmp_path / "docs/evaluation/behavior").exists()


@pytest.mark.base
def test_cli_success_output_is_stable_and_safe(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    result = evaluate_behavior.EvaluationRunResult(
        case_count=108,
        fixture_version="behavior-controlled-v1",
        model_count=9,
        output="mneme-behavior-evaluation",
        recorded=False,
    )
    monkeypatch.setattr(evaluate_behavior, "run", lambda **_: result)
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate_behavior", "--output", "/tmp/mneme-behavior-evaluation"],
    )

    evaluate_behavior.main()

    assert json.loads(capsys.readouterr().out) == {
        "cases": 108,
        "fixture_version": "behavior-controlled-v1",
        "models": 9,
        "output": "mneme-behavior-evaluation",
        "recorded": False,
        "status": "ok",
    }


@pytest.mark.base
@pytest.mark.parametrize(
    ("error", "exit_code", "code"),
    [
        (
            evaluate_behavior.BehaviorEvaluationInputError("private input detail"),
            2,
            "behavior_evaluation_input_invalid",
        ),
        (
            evaluate_behavior.BehaviorEvaluationWorktreeDirtyError(),
            2,
            "behavior_evaluation_worktree_dirty",
        ),
        (OSError("private output detail"), 1, "behavior_evaluation_unavailable"),
    ],
)
def test_cli_errors_have_stable_codes_without_internal_details(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
    exit_code: int,
    code: str,
) -> None:
    def fail(**kwargs: object) -> None:
        del kwargs
        raise error

    monkeypatch.setattr(evaluate_behavior, "run", fail)
    monkeypatch.setattr("sys.argv", ["evaluate_behavior", "--output", "/tmp/output"])

    with pytest.raises(SystemExit) as captured:
        evaluate_behavior.main()

    payload = json.loads(capsys.readouterr().err)
    assert captured.value.code == exit_code
    assert payload == {"error": code, "status": "error"}
    assert "private" not in json.dumps(payload)
