"""Sanitized source and environment provenance for recorded behavior runs."""

from __future__ import annotations

import platform
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict

from mneme.evaluation.behavior.fixtures import BehaviorFixtureFile
from mneme.evaluation.behavior.models import evaluation_models
from mneme.evaluation.behavior.reporting import sha256_file


class SourceIdentity(BaseModel):
    """Exact repository identity without a private filesystem path."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    revision: str
    branch: str
    dirty: bool


class EvaluationEnvironment(BaseModel):
    """Portable runtime facts needed to interpret a recorded run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-evaluation-environment-v1"] = (
        "behavior-evaluation-environment-v1"
    )
    python_version: str
    python_implementation: str
    uv_version: str
    operating_system: str
    operating_system_release: str
    machine: str
    processor: str
    timezone: Literal["UTC"] = "UTC"


class RunManifest(BaseModel):
    """Reproducibility identity for one exploratory or recorded run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal["behavior-evaluation-run-v1"] = "behavior-evaluation-run-v1"
    measured_at_utc: AwareDatetime
    recorded: bool
    controlled_synthetic: Literal[True] = True
    source: SourceIdentity
    fixture_version: str
    fixture_path: str
    fixture_sha256: str
    lockfile_path: str
    lockfile_sha256: str
    reference_time_utc: AwareDatetime
    evaluation_settings: dict[str, int | float]
    model_configurations: tuple[dict[str, object], ...]
    command: tuple[str, ...]
    score_rounding: str


def collect_source_identity(repo_root: Path) -> SourceIdentity:
    """Read exact Git identity without mutating the repository."""
    revision = _run_command(["git", "rev-parse", "HEAD"], cwd=repo_root)
    branch = _run_command(["git", "branch", "--show-current"], cwd=repo_root) or "DETACHED"
    dirty = bool(_run_command(["git", "status", "--porcelain"], cwd=repo_root))
    return SourceIdentity(revision=revision, branch=branch, dirty=dirty)


def collect_environment() -> EvaluationEnvironment:
    """Collect non-secret platform metadata for a reproducible run."""
    return EvaluationEnvironment(
        python_version=platform.python_version(),
        python_implementation=platform.python_implementation(),
        uv_version=_run_command(["uv", "--version"]),
        operating_system=platform.system(),
        operating_system_release=platform.release(),
        machine=platform.machine(),
        processor=platform.processor() or "unknown",
    )


def build_manifest(
    *,
    fixture: BehaviorFixtureFile,
    fixture_path: Path,
    lockfile_path: Path,
    repo_root: Path,
    recorded: bool,
    command: tuple[str, ...],
    measured_at: datetime | None = None,
    source: SourceIdentity | None = None,
) -> RunManifest:
    """Build a complete manifest with sanitized, repository-relative paths."""
    timestamp = measured_at or datetime.now(UTC)
    if timestamp.tzinfo is None:
        raise ValueError("Evaluation measurement time must be timezone-aware.")
    return RunManifest(
        measured_at_utc=timestamp.astimezone(UTC),
        recorded=recorded,
        source=source or collect_source_identity(repo_root),
        fixture_version=fixture.fixture_version,
        fixture_path=_safe_path_label(fixture_path, repo_root=repo_root),
        fixture_sha256=sha256_file(fixture_path),
        lockfile_path=_safe_path_label(lockfile_path, repo_root=repo_root),
        lockfile_sha256=sha256_file(lockfile_path),
        reference_time_utc=fixture.reference_time_utc,
        evaluation_settings=fixture.evaluation.model_dump(),
        model_configurations=tuple(model.configuration_payload() for model in evaluation_models()),
        command=command,
        score_rounding=(
            f"production scores rounded to 6 decimals; summaries rounded to "
            f"{fixture.evaluation.round_digits} decimals"
        ),
    )


def _safe_path_label(path: Path, *, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _run_command(command: list[str], *, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return completed.stdout.strip()


def runtime_command() -> tuple[str, ...]:
    """Return the portable interpreter identity used by the CLI manifest."""
    return (Path(sys.executable).name, "-m", "mneme.cli.evaluate_behavior")
