"""Tests for safe, exact behavior-evaluation provenance."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mneme.evaluation.behavior.fixtures import load_behavior_fixtures
from mneme.evaluation.behavior.provenance import (
    SourceIdentity,
    build_manifest,
    collect_environment,
    collect_source_identity,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "docs/evaluation/behavior/fixtures/behavior_controlled_v1.json"
LOCKFILE_PATH = REPO_ROOT / "backend/uv.lock"


@pytest.mark.base
def test_source_identity_reads_exact_git_state_without_a_path() -> None:
    source = collect_source_identity(REPO_ROOT)

    assert len(source.revision) == 40
    assert all(character in "0123456789abcdef" for character in source.revision)
    assert source.branch
    assert isinstance(source.dirty, bool)
    assert set(source.model_dump()) == {"revision", "branch", "dirty"}


@pytest.mark.base
def test_manifest_hashes_inputs_and_sanitizes_paths(tmp_path: Path) -> None:
    external_fixture = tmp_path / "controlled.json"
    external_fixture.write_bytes(FIXTURE_PATH.read_bytes())
    fixture = load_behavior_fixtures(external_fixture)
    source = SourceIdentity(revision="a" * 40, branch="test-branch", dirty=False)

    manifest = build_manifest(
        fixture=fixture,
        fixture_path=external_fixture,
        lockfile_path=LOCKFILE_PATH,
        repo_root=REPO_ROOT,
        recorded=False,
        command=("python", "-m", "mneme.cli.evaluate_behavior"),
        measured_at=datetime(2026, 7, 27, 12, 0, tzinfo=UTC),
        source=source,
    )
    serialized = json.dumps(manifest.model_dump(mode="json"), sort_keys=True)

    assert manifest.fixture_path == "controlled.json"
    assert manifest.lockfile_path == "backend/uv.lock"
    assert len(manifest.fixture_sha256) == len(manifest.lockfile_sha256) == 64
    assert manifest.source == source
    assert manifest.measured_at_utc == datetime(2026, 7, 27, 12, 0, tzinfo=UTC)
    assert manifest.controlled_synthetic is True
    assert len(manifest.model_configurations) == 9
    assert str(tmp_path) not in serialized
    assert "/home/" not in serialized
    assert "token" not in serialized.casefold()


@pytest.mark.base
def test_environment_is_portable_and_contains_no_process_secrets() -> None:
    environment = collect_environment()
    serialized = json.dumps(environment.model_dump(mode="json"), sort_keys=True)

    assert environment.schema_version == "behavior-evaluation-environment-v1"
    assert environment.python_version
    assert environment.uv_version.startswith("uv ")
    assert environment.operating_system
    assert environment.timezone == "UTC"
    assert "token" not in serialized.casefold()
    assert "/home/" not in serialized


@pytest.mark.base
def test_manifest_rejects_a_naive_measurement_timestamp() -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)

    with pytest.raises(ValueError, match="timezone-aware"):
        build_manifest(
            fixture=fixture,
            fixture_path=FIXTURE_PATH,
            lockfile_path=LOCKFILE_PATH,
            repo_root=REPO_ROOT,
            recorded=True,
            command=("python", "-m", "mneme.cli.evaluate_behavior", "--recorded"),
            measured_at=datetime(2026, 7, 27, 12, 0),
            source=SourceIdentity(revision="a" * 40, branch="test", dirty=False),
        )
