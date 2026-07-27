"""Tests for stable and atomic behavior-evaluation artifacts."""

import csv
import json
from pathlib import Path

import pytest

from mneme.evaluation.behavior.analysis import build_summary
from mneme.evaluation.behavior.fixtures import load_behavior_fixtures
from mneme.evaluation.behavior.harness import run_behavior_evaluation
from mneme.evaluation.behavior.reporting import (
    sha256_file,
    write_case_results,
    write_summary_csv,
    write_summary_json,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs/evaluation/behavior/fixtures/behavior_controlled_v1.json"
)


@pytest.mark.base
def test_artifact_writers_are_stable_complete_and_machine_readable(tmp_path: Path) -> None:
    fixture = load_behavior_fixtures(FIXTURE_PATH)
    cases = run_behavior_evaluation(fixture)
    summary = build_summary(fixture, cases)
    raw_path = tmp_path / "raw/case_results.jsonl"
    json_path = tmp_path / "summary.json"
    csv_path = tmp_path / "summary.csv"

    write_case_results(raw_path, cases)
    write_summary_json(json_path, summary)
    write_summary_csv(csv_path, summary)
    first_bytes = (raw_path.read_bytes(), json_path.read_bytes(), csv_path.read_bytes())
    write_case_results(raw_path, cases)
    write_summary_json(json_path, summary)
    write_summary_csv(csv_path, summary)

    assert first_bytes == (raw_path.read_bytes(), json_path.read_bytes(), csv_path.read_bytes())
    raw = [json.loads(line) for line in raw_path.read_text().splitlines()]
    assert len(raw) == len(cases) == 108
    assert [(row["scenario_id"], row["model_id"]) for row in raw] == sorted(
        (row["scenario_id"], row["model_id"]) for row in raw
    )
    summary_payload = json.loads(json_path.read_text())
    assert summary_payload["controlled_synthetic"] is True
    assert summary_payload["invariant_failures"] == []

    with csv_path.open(newline="") as source:
        rows = list(csv.DictReader(source))
    assert len(rows) == len(summary.aggregates) + len(summary.paired_comparisons)
    assert {row["record_type"] for row in rows} == {"aggregate", "paired_delta"}


@pytest.mark.base
def test_sha256_file_returns_a_stable_lowercase_digest(tmp_path: Path) -> None:
    artifact = tmp_path / "artifact.txt"
    artifact.write_text("abc", encoding="utf-8")

    assert sha256_file(artifact) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


@pytest.mark.base
def test_failed_atomic_replace_leaves_no_partial_destination(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mneme.evaluation.behavior import reporting

    destination = tmp_path / "summary.json"

    def fail_replace(source: str, target: Path) -> None:
        del source, target
        raise OSError("controlled write failure")

    monkeypatch.setattr(reporting.os, "replace", fail_replace)
    with pytest.raises(OSError, match="controlled write failure"):
        reporting.write_json_payload(destination, {"status": "partial"})

    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []
