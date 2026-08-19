"""Offline CLI for controlled, reproducible behavior-model evaluation."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import NoReturn

from pydantic import ValidationError

from mneme.evaluation.behavior.analysis import build_summary
from mneme.evaluation.behavior.fixtures import load_behavior_fixtures
from mneme.evaluation.behavior.harness import run_behavior_evaluation
from mneme.evaluation.behavior.provenance import (
    build_manifest,
    collect_environment,
    collect_source_identity,
    runtime_command,
)
from mneme.evaluation.behavior.reporting import (
    write_case_results,
    write_json_payload,
    write_summary_csv,
    write_summary_json,
)

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_FIXTURE = REPO_ROOT / "docs/evaluation/behavior/fixtures/behavior_controlled_v1.json"


class BehaviorEvaluationInputError(ValueError):
    """Raised when CLI mode and path arguments are inconsistent."""


class BehaviorEvaluationWorktreeDirtyError(RuntimeError):
    """Raised before a recorded run can overwrite formal artifacts."""


@dataclass(frozen=True, slots=True)
class EvaluationRunResult:
    """Safe completion metadata printed by the CLI."""

    case_count: int
    fixture_version: str
    model_count: int
    output: str
    recorded: bool


def build_parser() -> argparse.ArgumentParser:
    """Build exploratory and recorded evaluation arguments."""
    parser = argparse.ArgumentParser(
        description="Evaluate behavior models on the controlled synthetic fixture."
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=DEFAULT_FIXTURE,
        help="versioned controlled fixture JSON",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="exploratory artifact directory, normally under /tmp",
    )
    parser.add_argument(
        "--recorded",
        action="store_true",
        help="require a clean tree and write the formal repository artifacts",
    )
    return parser


def run(
    *,
    fixture_path: Path,
    output_dir: Path | None,
    recorded: bool,
    repo_root: Path = REPO_ROOT,
    measured_at: datetime | None = None,
) -> EvaluationRunResult:
    """Run offline replay and write all raw and summary artifacts."""
    if recorded and output_dir is not None:
        raise BehaviorEvaluationInputError("Recorded mode fixes the artifact destination.")
    if not recorded and output_dir is None:
        raise BehaviorEvaluationInputError("Exploratory mode requires --output.")

    source = collect_source_identity(repo_root)
    if recorded and source.dirty:
        raise BehaviorEvaluationWorktreeDirtyError
    destination = repo_root / "docs/evaluation/behavior" if recorded else output_dir
    assert destination is not None

    fixture = load_behavior_fixtures(fixture_path)
    cases = run_behavior_evaluation(fixture)
    summary = build_summary(fixture, cases)
    manifest = build_manifest(
        fixture=fixture,
        fixture_path=fixture_path,
        lockfile_path=repo_root / "backend/uv.lock",
        repo_root=repo_root,
        recorded=recorded,
        command=_manifest_command(
            fixture_path=fixture_path,
            output_dir=destination,
            recorded=recorded,
            repo_root=repo_root,
        ),
        measured_at=measured_at,
        source=source,
    )
    environment = collect_environment()

    write_case_results(destination / "raw/case_results.jsonl", cases)
    write_json_payload(destination / "raw/run_manifest.json", manifest)
    write_json_payload(destination / "raw/environment.json", environment)
    write_summary_json(destination / "summary.json", summary)
    write_summary_csv(destination / "summary.csv", summary)
    return EvaluationRunResult(
        case_count=len(cases),
        fixture_version=fixture.fixture_version,
        model_count=len(summary.model_configurations),
        output=_safe_output_label(destination, repo_root=repo_root),
        recorded=recorded,
    )


def main() -> None:
    """Run the selected mode with stable machine-readable exit contracts."""
    arguments = build_parser().parse_args()
    try:
        result = run(
            fixture_path=arguments.fixture,
            output_dir=arguments.output,
            recorded=arguments.recorded,
        )
    except BehaviorEvaluationWorktreeDirtyError:
        _exit_error("behavior_evaluation_worktree_dirty", exit_code=2)
    except (BehaviorEvaluationInputError, ValidationError, FileNotFoundError):
        _exit_error("behavior_evaluation_input_invalid", exit_code=2)
    except Exception:
        _exit_error("behavior_evaluation_unavailable", exit_code=1)

    print(
        json.dumps(
            {
                "cases": result.case_count,
                "fixture_version": result.fixture_version,
                "models": result.model_count,
                "output": result.output,
                "recorded": result.recorded,
                "status": "ok",
            },
            sort_keys=True,
        )
    )


def _manifest_command(
    *,
    fixture_path: Path,
    output_dir: Path,
    recorded: bool,
    repo_root: Path,
) -> tuple[str, ...]:
    base = runtime_command()
    if recorded:
        return (*base, "--recorded")
    return (
        *base,
        "--fixture",
        _safe_output_label(fixture_path, repo_root=repo_root),
        "--output",
        output_dir.name,
    )


def _safe_output_label(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _exit_error(error: str, *, exit_code: int) -> NoReturn:
    print(json.dumps({"error": error, "status": "error"}, sort_keys=True), file=sys.stderr)
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
