"""Stable, atomic serialization for controlled behavior evaluation artifacts."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import tempfile
from collections.abc import Mapping, Sequence
from contextlib import suppress
from pathlib import Path

from pydantic import BaseModel

from mneme.evaluation.behavior.analysis import BehaviorEvaluationSummary
from mneme.evaluation.behavior.models import BehaviorCaseResult


def sha256_file(path: Path) -> str:
    """Return the lowercase SHA-256 digest of one artifact."""
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_case_results(path: Path, cases: Sequence[BehaviorCaseResult]) -> None:
    """Write sorted JSONL with one complete scenario-model result per line."""
    lines = [
        json.dumps(case.model_dump(mode="json"), separators=(",", ":"), sort_keys=True)
        for case in sorted(cases, key=lambda item: (item.scenario_id, item.model_id))
    ]
    _atomic_write(path, "\n".join(lines) + "\n")


def write_summary_json(path: Path, summary: BehaviorEvaluationSummary) -> None:
    """Write the full descriptive summary as stable indented JSON."""
    _write_json(path, summary)


def write_summary_csv(path: Path, summary: BehaviorEvaluationSummary) -> None:
    """Write flat aggregate and paired-difference rows for plotting."""
    columns = (
        "record_type",
        "model_id",
        "comparator_model",
        "scenario_family",
        "metric",
        "applicable_n",
        "mean",
        "median",
        "interval_lower",
        "interval_upper",
    )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for row in summary.aggregates:
        writer.writerow(
            {
                "record_type": "aggregate",
                "model_id": row.model_id,
                "comparator_model": "",
                "scenario_family": row.scenario_family.value
                if row.scenario_family is not None
                else "all",
                "metric": row.metric,
                "applicable_n": row.applicable_n,
                "mean": row.mean,
                "median": row.median,
                "interval_lower": "",
                "interval_upper": "",
            }
        )
    for row in summary.paired_comparisons:
        writer.writerow(
            {
                "record_type": "paired_delta",
                "model_id": row.reference_model,
                "comparator_model": row.comparator_model,
                "scenario_family": "all",
                "metric": row.metric,
                "applicable_n": row.applicable_n,
                "mean": row.mean_delta,
                "median": row.median_delta,
                "interval_lower": row.interval_lower,
                "interval_upper": row.interval_upper,
            }
        )
    _atomic_write(path, output.getvalue())


def write_json_payload(path: Path, payload: BaseModel | Mapping[str, object]) -> None:
    """Write a validated model or explicit mapping as stable JSON."""
    _write_json(path, payload)


def _write_json(path: Path, payload: BaseModel | Mapping[str, object]) -> None:
    data = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else dict(payload)
    _atomic_write(path, json.dumps(data, indent=2, sort_keys=True) + "\n")


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as destination:
            destination.write(content)
            destination.flush()
            os.fsync(destination.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        with suppress(FileNotFoundError):
            os.unlink(temporary_name)
        raise
