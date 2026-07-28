#!/usr/bin/env python3
"""Validate and summarize the paired seed artifact-reuse experiment."""

from __future__ import annotations

import argparse
import csv
import json
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

FIXED_SEEDS = ("1706.03762", "2010.11929", "2106.09685")
EXPECTED_PAPER_COUNT = 5
SUCCEEDED = "succeeded"
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{7,64}")
HASH_FIELDS = frozenset(
    {
        "app_apk_sha256",
        "test_apk_sha256",
        "runner_sha256",
        "inspector_sha256",
        "analyzer_sha256",
        "android_test_sources_sha256",
    }
)


@dataclass(frozen=True)
class PairResult:
    pair_id: str
    seed_arxiv_id: str
    first_duration_ms: float
    reuse_duration_ms: float
    difference_ms: float
    reuse_to_first_ratio: float
    paper_ids: str
    job_count: int
    paper_versions: int
    paper_summaries: int
    paper_chunks: int
    storage_files: int
    artifact_checksum_sha256: str


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the three preregistered first-versus-artifact-reuse pairs "
            "and write descriptive results."
        )
    )
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required experiment artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def read_single_csv_row(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required Android measurement: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(
            f"Expected exactly one raw measurement row in {path}; got {len(rows)}."
        )
    return rows[0]


def parse_success(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Invalid Boolean value: {value!r}")
    return normalized == "true"


def validate_android_row(
    row: dict[str, str],
    *,
    pair_id: str,
    seed: str,
    condition: str,
) -> tuple[float, tuple[str, ...]]:
    expected = {
        "schema_version": "seed-artifact-reuse-android-v1",
        "pair_id": pair_id,
        "seed_arxiv_id": seed,
        "condition": condition,
        "content_origin": "LIVE_BACKEND",
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ValueError(
                f"{pair_id}/{condition} has {field}={row.get(field)!r}; expected {value!r}."
            )
    if not parse_success(row.get("success", "")):
        raise ValueError(
            f"{pair_id}/{condition} failed and remains in raw data: {row.get('outcome')!r}."
        )
    if row.get("outcome") != "live_five_paper_briefing_visible":
        raise ValueError(
            f"{pair_id}/{condition} did not reach the visible briefing criterion."
        )
    if int(row.get("paper_count", "0")) != EXPECTED_PAPER_COUNT:
        raise ValueError(f"{pair_id}/{condition} did not return exactly five papers.")
    paper_ids = tuple(item for item in row.get("paper_ids", "").split(";") if item)
    if (
        len(paper_ids) != EXPECTED_PAPER_COUNT
        or len(set(paper_ids)) != EXPECTED_PAPER_COUNT
    ):
        raise ValueError(f"{pair_id}/{condition} has invalid paper identifiers.")
    duration = float(row.get("duration_ms", ""))
    if duration <= 0:
        raise ValueError(f"{pair_id}/{condition} has a non-positive duration.")
    return duration, paper_ids


def validate_backend_snapshot(
    snapshot: dict[str, Any],
    *,
    run_id: str,
    pair_id: str,
    seed: str,
    phase: str,
    database_name: str,
    redis_instance_port: int,
    redis_database: int,
    queue_name: str,
) -> None:
    expected = {
        "schema_version": "seed-artifact-reuse-backend-snapshot-v1",
        "run_id": run_id,
        "pair_id": pair_id,
        "seed_arxiv_id": seed,
        "phase": phase,
        "secrets_retained": False,
        "redis_instance_host": "127.0.0.1",
        "redis_instance_port": redis_instance_port,
        "redis_database": redis_database,
        "queue_name": queue_name,
        "storage_namespace": database_name,
    }
    for field, value in expected.items():
        if snapshot.get(field) != value:
            raise ValueError(
                f"{pair_id}/{phase} has {field}={snapshot.get(field)!r}; expected {value!r}."
            )
    if snapshot.get("database_name") != database_name or not database_name.startswith(
        "mneme_eval_"
    ):
        raise ValueError(
            f"{pair_id}/{phase} was not measured in a disposable database."
        )
    job_count = snapshot.get("job_count")
    if not isinstance(job_count, int) or job_count < 1:
        raise ValueError(f"{pair_id}/{phase} contains no pipeline jobs.")
    if snapshot.get("job_status_counts") != {SUCCEEDED: job_count}:
        raise ValueError(f"{pair_id}/{phase} contains a non-succeeded pipeline job.")
    settled_window = snapshot.get("settled_window")
    if (
        not isinstance(settled_window, dict)
        or not isinstance(settled_window.get("poll_seconds"), (int, float))
        or settled_window["poll_seconds"] <= 0
        or not isinstance(settled_window.get("quiet_polls"), int)
        or settled_window["quiet_polls"] < 3
        or settled_window.get("requires_identical_job_fingerprint") is not True
    ):
        raise ValueError(
            f"{pair_id}/{phase} did not retain the required quiet-window evidence."
        )
    jobs = snapshot.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != job_count:
        raise ValueError(f"{pair_id}/{phase} has an inconsistent job list.")
    if len({job_identity(job) for job in jobs}) != job_count:
        raise ValueError(f"{pair_id}/{phase} has duplicate durable job identities.")
    for job in jobs:
        if (
            job.get("status") != SUCCEEDED
            or not isinstance(job.get("id"), str)
            or not isinstance(job.get("idempotency_key"), str)
            or not isinstance(job.get("attempt_count"), int)
            or job["attempt_count"] < 1
        ):
            raise ValueError(f"{pair_id}/{phase} has an invalid durable job record.")
    counts = snapshot.get("artifact_counts")
    if not isinstance(counts, dict) or any(
        not isinstance(counts.get(field), int) or counts[field] < 1
        for field in (
            "paper_versions",
            "paper_summaries",
            "paper_chunks",
            "storage_files",
        )
    ):
        raise ValueError(f"{pair_id}/{phase} has an incomplete artifact inventory.")
    checksum = snapshot.get("artifact_checksum_sha256")
    if not isinstance(checksum, str) or SHA256_PATTERN.fullmatch(checksum) is None:
        raise ValueError(f"{pair_id}/{phase} has an invalid artifact checksum.")
    storage_files = snapshot.get("storage_files")
    if (
        not isinstance(storage_files, list)
        or len(storage_files) != counts["storage_files"]
    ):
        raise ValueError(f"{pair_id}/{phase} has an inconsistent storage inventory.")
    for item in storage_files:
        relative_path = item.get("relative_path")
        file_checksum = item.get("sha256")
        size_bytes = item.get("size_bytes")
        if (
            not isinstance(relative_path, str)
            or Path(relative_path).is_absolute()
            or ".." in Path(relative_path).parts
            or not isinstance(file_checksum, str)
            or SHA256_PATTERN.fullmatch(file_checksum) is None
            or not isinstance(size_bytes, int)
            or size_bytes < 0
        ):
            raise ValueError(f"{pair_id}/{phase} has an invalid stored-file record.")
    storage_identity = snapshot.get("storage_identity_sha256")
    if (
        not isinstance(storage_identity, str)
        or SHA256_PATTERN.fullmatch(storage_identity) is None
    ):
        raise ValueError(f"{pair_id}/{phase} has an invalid storage identity.")
    paper_artifacts = snapshot.get("paper_artifacts")
    if not isinstance(paper_artifacts, list) or not paper_artifacts:
        raise ValueError(
            f"{pair_id}/{phase} has no secret-free per-paper artifact manifest."
        )
    paper_ids = [item.get("paper_id") for item in paper_artifacts]
    if not all(isinstance(item, str) for item in paper_ids) or len(
        set(paper_ids)
    ) != len(paper_ids):
        raise ValueError(
            f"{pair_id}/{phase} has invalid per-paper artifact identities."
        )


def validate_ui_paper_artifacts(
    snapshot: dict[str, Any],
    paper_ids: tuple[str, ...],
    *,
    pair_id: str,
    phase: str,
) -> None:
    by_id = {item["paper_id"]: item for item in snapshot["paper_artifacts"]}
    for paper_id in paper_ids:
        artifact = by_id.get(paper_id)
        if artifact is None:
            raise ValueError(
                f"{pair_id}/{phase} has no artifacts for UI paper {paper_id}."
            )
        if any(
            not isinstance(artifact.get(field), int) or artifact[field] < 1
            for field in ("version_count", "summary_count", "chunk_count", "job_count")
        ):
            raise ValueError(
                f"{pair_id}/{phase} has incomplete artifacts for UI paper {paper_id}."
            )
        checksum = artifact.get("artifact_checksum_sha256")
        if not isinstance(checksum, str) or SHA256_PATTERN.fullmatch(checksum) is None:
            raise ValueError(
                f"{pair_id}/{phase} has an invalid UI-paper artifact checksum."
            )


def job_identity(job: dict[str, Any]) -> tuple[Any, ...]:
    return (
        job.get("id"),
        job.get("idempotency_key"),
        job.get("stage"),
        job.get("paper_id"),
        job.get("paper_version_id"),
    )


def validate_backend_reuse(
    first: dict[str, Any],
    reuse: dict[str, Any],
    *,
    pair_id: str,
) -> None:
    if first.get("database_name") != reuse.get("database_name"):
        raise ValueError(f"{pair_id} did not reuse the same disposable database.")
    for field in (
        "redis_instance_host",
        "redis_instance_port",
        "redis_database",
        "queue_name",
        "storage_namespace",
        "storage_identity_sha256",
    ):
        if first.get(field) != reuse.get(field):
            raise ValueError(
                f"{pair_id} changed its isolated {field} between conditions."
            )
    first_jobs = {job_identity(job): job for job in first["jobs"]}
    reuse_jobs = {job_identity(job): job for job in reuse["jobs"]}
    if first_jobs.keys() != reuse_jobs.keys():
        raise ValueError(
            f"{pair_id} created, removed, or replaced a durable pipeline job."
        )
    for identity in first_jobs:
        first_attempts = int(first_jobs[identity]["attempt_count"])
        reuse_attempts = int(reuse_jobs[identity]["attempt_count"])
        if reuse_attempts != first_attempts:
            raise ValueError(
                f"{pair_id} changed attempt_count for durable job {identity[0]} "
                f"from {first_attempts} to {reuse_attempts}."
            )
    if first.get("artifact_counts") != reuse.get("artifact_counts"):
        raise ValueError(
            f"{pair_id} changed the immutable artifact inventory during reuse."
        )
    if first.get("artifact_checksum_sha256") != reuse.get("artifact_checksum_sha256"):
        raise ValueError(f"{pair_id} changed an immutable artifact during reuse.")
    if first.get("paper_artifacts") != reuse.get("paper_artifacts"):
        raise ValueError(
            f"{pair_id} changed its per-paper artifact manifest during reuse."
        )


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != "seed-artifact-reuse-run-manifest-v1":
        raise ValueError("The run manifest schema is not supported.")
    if manifest.get("fixed_seeds") != list(FIXED_SEEDS):
        raise ValueError(
            "The run manifest does not contain the three fixed seeds in order."
        )
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith("mneme_eval_"):
        raise ValueError("The run manifest has an invalid disposable run identifier.")
    revision = manifest.get("repository_revision")
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("The run manifest has an invalid repository revision.")
    if (
        not isinstance(manifest.get("measured_at_utc"), str)
        or not manifest["measured_at_utc"]
    ):
        raise ValueError("The run manifest is missing its UTC measurement time.")
    protocol_flags = {
        "android_data_cleared_before_each_condition": True,
        "backend_state_preserved_between_first_and_reuse": True,
        "dedicated_redis_instance_per_pair": True,
        "failed_runs_retried": False,
        "source_tree_clean_at_start": True,
        "token_retained": False,
    }
    for field, expected in protocol_flags.items():
        if manifest.get(field) is not expected:
            raise ValueError(f"The run manifest has an invalid {field} protocol flag.")
    if (
        manifest.get("timing_endpoint")
        != "Immediately before submit click to visible live five-paper briefing."
    ):
        raise ValueError("The run manifest has an invalid timing endpoint.")
    if manifest.get("finish_tree_gate") != "passed":
        raise ValueError(
            "The run manifest did not pass its finish-time source-tree gate."
        )
    for section, fields in {
        "device_environment": (
            "serial",
            "model",
            "product",
            "android_release",
            "android_api",
            "boot_id",
            "webview_provider",
        ),
        "host_environment": (
            "logical_cpus",
            "memory_kib",
            "load_average_1m_5m_15m",
            "kernel",
        ),
    }.items():
        payload = manifest.get(section)
        if not isinstance(payload, dict) or any(
            not isinstance(payload.get(field), str) or not payload[field]
            for field in fields
        ):
            raise ValueError(f"The run manifest has incomplete {section} provenance.")
    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict) or set(hashes) != HASH_FIELDS:
        raise ValueError("The run manifest has an incomplete provenance hash set.")
    for field, value in hashes.items():
        if not isinstance(value, str) or SHA256_PATTERN.fullmatch(value) is None:
            raise ValueError(f"The run manifest has an invalid {field} value.")
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list) or len(pairs) != len(FIXED_SEEDS):
        raise ValueError("The run manifest must contain exactly three pairs.")
    redis_ports: list[int] = []
    database_names: list[str] = []
    queue_names: list[str] = []
    for index, (pair, seed) in enumerate(zip(pairs, FIXED_SEEDS, strict=True), start=1):
        expected_pair = f"pair_{index:02d}"
        if not isinstance(pair, dict):
            raise ValueError("Each manifest pair must be an object.")
        if pair.get("pair_id") != expected_pair or pair.get("seed_arxiv_id") != seed:
            raise ValueError(
                f"Manifest pair {index} does not match the fixed protocol."
            )
        relative_dir = pair.get("relative_dir")
        if (
            not isinstance(relative_dir, str)
            or Path(relative_dir).is_absolute()
            or ".." in Path(relative_dir).parts
        ):
            raise ValueError(
                f"Manifest pair {index} has an invalid relative directory."
            )
        redis_database = pair.get("redis_database")
        if not isinstance(redis_database, int) or redis_database != 0:
            raise ValueError(f"Manifest pair {index} has an invalid Redis database.")
        redis_port = pair.get("redis_instance_port")
        if not isinstance(redis_port, int) or not 1024 <= redis_port <= 65535:
            raise ValueError(
                f"Manifest pair {index} has an invalid dedicated Redis port."
            )
        redis_ports.append(redis_port)
        database_name = pair.get("database_name")
        expected_database = f"{run_id}_{expected_pair}"
        if database_name != expected_database:
            raise ValueError(
                f"Manifest pair {index} has an invalid disposable database name."
            )
        database_names.append(database_name)
        queue_name = pair.get("queue_name")
        expected_queue = f"mneme:jobs:eval:{run_id}:{expected_pair}"
        if queue_name != expected_queue:
            raise ValueError(
                f"Manifest pair {index} has an invalid isolated queue name."
            )
        queue_names.append(queue_name)
    if len(set(redis_ports)) != len(redis_ports):
        raise ValueError("Each pair must use a different dedicated Redis instance.")
    if len(set(database_names)) != len(database_names) or len(set(queue_names)) != len(
        queue_names
    ):
        raise ValueError("Each pair must use a different database and queue.")
    return pairs


def analyze(run_dir: Path) -> list[PairResult]:
    manifest = read_json(run_dir / "run_manifest.json")
    pairs = validate_manifest(manifest)
    run_id = manifest["run_id"]
    results: list[PairResult] = []
    for pair in pairs:
        pair_id = pair["pair_id"]
        seed = pair["seed_arxiv_id"]
        pair_dir = run_dir / pair["relative_dir"]
        first_duration, first_papers = validate_android_row(
            read_single_csv_row(pair_dir / "first" / "android_measurement.csv"),
            pair_id=pair_id,
            seed=seed,
            condition="first",
        )
        reuse_duration, reuse_papers = validate_android_row(
            read_single_csv_row(pair_dir / "reuse" / "android_measurement.csv"),
            pair_id=pair_id,
            seed=seed,
            condition="reuse",
        )
        if first_papers != reuse_papers:
            raise ValueError(
                f"{pair_id} returned different ordered paper identifiers on reuse."
            )

        first_snapshot = read_json(pair_dir / "after_first_backend.json")
        reuse_snapshot = read_json(pair_dir / "after_reuse_backend.json")
        validate_backend_snapshot(
            first_snapshot,
            run_id=run_id,
            pair_id=pair_id,
            seed=seed,
            phase="after_first",
            database_name=pair["database_name"],
            redis_instance_port=pair["redis_instance_port"],
            redis_database=pair["redis_database"],
            queue_name=pair["queue_name"],
        )
        validate_backend_snapshot(
            reuse_snapshot,
            run_id=run_id,
            pair_id=pair_id,
            seed=seed,
            phase="after_reuse",
            database_name=pair["database_name"],
            redis_instance_port=pair["redis_instance_port"],
            redis_database=pair["redis_database"],
            queue_name=pair["queue_name"],
        )
        validate_ui_paper_artifacts(
            first_snapshot,
            first_papers,
            pair_id=pair_id,
            phase="after_first",
        )
        validate_ui_paper_artifacts(
            reuse_snapshot,
            reuse_papers,
            pair_id=pair_id,
            phase="after_reuse",
        )
        validate_backend_reuse(first_snapshot, reuse_snapshot, pair_id=pair_id)
        counts = first_snapshot["artifact_counts"]
        results.append(
            PairResult(
                pair_id=pair_id,
                seed_arxiv_id=seed,
                first_duration_ms=first_duration,
                reuse_duration_ms=reuse_duration,
                difference_ms=reuse_duration - first_duration,
                reuse_to_first_ratio=reuse_duration / first_duration,
                paper_ids=";".join(first_papers),
                job_count=first_snapshot["job_count"],
                paper_versions=counts["paper_versions"],
                paper_summaries=counts["paper_summaries"],
                paper_chunks=counts["paper_chunks"],
                storage_files=counts["storage_files"],
                artifact_checksum_sha256=first_snapshot["artifact_checksum_sha256"],
            )
        )
    return results


def write_results(output_dir: Path, results: list[PairResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(result) for result in results]
    with (output_dir / "paired_results.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    first_values = [result.first_duration_ms for result in results]
    reuse_values = [result.reuse_duration_ms for result in results]
    summary = {
        "schema_version": "seed-artifact-reuse-analysis-v1",
        "pair_count": len(results),
        "all_pairs_valid": True,
        "first_duration_ms": {
            "values": first_values,
            "median": statistics.median(first_values),
            "minimum": min(first_values),
            "maximum": max(first_values),
            "range_ms": max(first_values) - min(first_values),
        },
        "reuse_duration_ms": {
            "values": reuse_values,
            "median": statistics.median(reuse_values),
            "minimum": min(reuse_values),
            "maximum": max(reuse_values),
            "range_ms": max(reuse_values) - min(reuse_values),
        },
        "paired_results": rows,
        "interpretation_boundary": (
            "Three fixed paired observations of seed-to-visible-briefing latency. "
            "The reuse condition preserves all reuse-eligible backend state; immutable jobs "
            "and artifacts are verified, but this is not a causal isolation of artifact caching. "
            "Descriptive median and range only; no percentile, confidence interval, "
            "significance test, or population claim."
        ),
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    arguments = parse_arguments()
    run_dir = arguments.run_dir.resolve()
    output_dir = (arguments.output_dir or run_dir / "analysis").resolve()
    results = analyze(run_dir)
    write_results(output_dir, results)
    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "pair_count": len(results),
                "status": "ok",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
