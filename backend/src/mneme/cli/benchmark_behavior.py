"""CLI for the recorded environment-sensitive behavior performance benchmark."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, NoReturn

from pydantic import AwareDatetime, BaseModel, ConfigDict

from mneme.evaluation.behavior.performance import run_behavior_performance_benchmark
from mneme.evaluation.behavior.performance_models import (
    DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG,
    BehaviorPerformanceConfig,
    BehaviorPerformanceResult,
)
from mneme.evaluation.behavior.provenance import (
    EvaluationEnvironment,
    SourceIdentity,
    collect_environment,
    collect_source_identity,
)
from mneme.evaluation.behavior.reporting import write_json_payload

REPO_ROOT = Path(__file__).resolve().parents[4]


class BehaviorBenchmarkWorktreeDirtyError(RuntimeError):
    """Raised before a retained benchmark starts from a dirty source tree."""


class BehaviorPerformanceArtifact(BaseModel):
    """Retained benchmark data with sanitized source and environment identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-performance-artifact-v1"] = "behavior-performance-artifact-v1"
    measured_at_utc: AwareDatetime
    source: SourceIdentity
    environment: EvaluationEnvironment
    command: tuple[str, ...]
    benchmark: BehaviorPerformanceResult


@dataclass(frozen=True, slots=True)
class BenchmarkRunResult:
    """Safe completion metadata printed by the CLI."""

    case_count: int
    output: str
    repetitions: int


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit output and clean-tree benchmark arguments."""
    parser = argparse.ArgumentParser(
        description="Benchmark behavior-v2 aggregation and ranking at frozen scales."
    )
    parser.add_argument("--output", type=Path, required=True, help="performance JSON path")
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="refuse measurement when the repository has tracked or untracked changes",
    )
    return parser


def run(
    *,
    output_path: Path,
    require_clean: bool,
    config: BehaviorPerformanceConfig = DEFAULT_BEHAVIOR_PERFORMANCE_CONFIG,
    repo_root: Path = REPO_ROOT,
    measured_at: datetime | None = None,
) -> BenchmarkRunResult:
    """Run the frozen benchmark and atomically retain its raw timing samples."""
    source = collect_source_identity(repo_root)
    if require_clean and source.dirty:
        raise BehaviorBenchmarkWorktreeDirtyError
    timestamp = measured_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("Behavior benchmark measurement time must be timezone-aware.")
    benchmark = run_behavior_performance_benchmark(config)
    artifact = BehaviorPerformanceArtifact(
        measured_at_utc=timestamp.astimezone(UTC),
        source=source,
        environment=collect_environment(),
        command=(
            Path(sys.executable).name,
            "-m",
            "mneme.cli.benchmark_behavior",
            "--output",
            output_path.name,
            *(("--require-clean",) if require_clean else ()),
        ),
        benchmark=benchmark,
    )
    write_json_payload(output_path, artifact)
    return BenchmarkRunResult(
        case_count=len(benchmark.cases),
        output=_safe_output_label(output_path, repo_root=repo_root),
        repetitions=benchmark.measured_repetitions,
    )


def main() -> None:
    """Execute with stable, non-sensitive JSON stdout and error contracts."""
    arguments = build_parser().parse_args()
    try:
        result = run(
            output_path=arguments.output,
            require_clean=arguments.require_clean,
        )
    except BehaviorBenchmarkWorktreeDirtyError:
        _exit_error("behavior_benchmark_worktree_dirty", exit_code=2)
    except (OSError, ValueError):
        _exit_error("behavior_benchmark_input_invalid", exit_code=2)
    except Exception:
        _exit_error("behavior_benchmark_unavailable", exit_code=1)
    print(
        json.dumps(
            {
                "cases": result.case_count,
                "output": result.output,
                "repetitions": result.repetitions,
                "status": "ok",
            },
            sort_keys=True,
        )
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
