#!/usr/bin/env python3
"""Validate and summarize three one-shot seed first-initialization trials."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

FIXED_SEEDS = ("1706.03762", "2010.11929", "2106.09685")
EXPECTED_FIELDS = (
    "schema_version",
    "trial_id",
    "seed_arxiv_id",
    "duration_ms",
    "success",
    "outcome",
    "paper_count",
    "paper_ids",
    "content_origin",
)
EXPECTED_PAPER_COUNT = 5
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
REVISION_PATTERN = re.compile(r"[0-9a-f]{7,64}")
CANDIDATE_SOURCES = frozenset({"citation_graph", "same_category_fallback"})
EMPTY_DOMAIN_TABLES = frozenset(
    {
        "papers",
        "paper_versions",
        "paper_summaries",
        "paper_chunks",
        "pipeline_jobs",
        "digests",
        "digest_entries",
        "citations",
        "authors",
        "paper_authors",
        "user_events",
        "qa_conversations",
        "qa_messages",
    }
)


@dataclass(frozen=True)
class TrialResult:
    trial_id: str
    seed_arxiv_id: str
    duration_ms: float
    candidate_source: str
    api_request_duration_ms: float
    paper_count: int
    paper_ids: str


def parse_arguments() -> argparse.Namespace:
    if sys.argv[1:] == ["--self-test"]:
        return argparse.Namespace(command="self-test")
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate-trial")
    validate.add_argument("--run-dir", type=Path, required=True)
    validate.add_argument("--trial-id", required=True)
    analyze = subparsers.add_parser("analyze")
    analyze.add_argument("--run-dir", type=Path, required=True)
    analyze.add_argument("--output-dir", type=Path)
    return parser.parse_args()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing required artifact: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object: {path}")
    return payload


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def expected_trial_id(index: int) -> str:
    return f"trial_{index:02d}"


def validate_manifest(manifest: dict[str, Any], *, require_finished: bool) -> list[dict[str, Any]]:
    if manifest.get("schema_version") != "seed-first-initialization-run-manifest-v1":
        raise ValueError("Unsupported seed first-initialization manifest schema.")
    run_id = manifest.get("run_id")
    if not isinstance(run_id, str) or not run_id.startswith("mneme_eval_si_"):
        raise ValueError("Manifest has an invalid disposable run ID.")
    if manifest.get("fixed_seeds") != list(FIXED_SEEDS):
        raise ValueError("Manifest does not contain the three fixed seeds in order.")
    revision = manifest.get("repository_revision")
    if not isinstance(revision, str) or REVISION_PATTERN.fullmatch(revision) is None:
        raise ValueError("Manifest repository revision is invalid.")
    expected_flags = {
        "one_measurement_per_seed": True,
        "automatic_experiment_retry_enabled": False,
        "android_data_cleared_before_each_trial": True,
        "fresh_database_per_trial": True,
        "fresh_redis_per_trial": True,
        "fresh_storage_per_trial": True,
        "fresh_user_per_trial": True,
        "source_tree_clean_at_start": True,
        "token_retained": False,
    }
    for field, value in expected_flags.items():
        if manifest.get(field) is not value:
            raise ValueError(f"Manifest has invalid protocol flag {field}.")
    if (
        manifest.get("timing_endpoint")
        != "Immediately before submit click to visible live five-paper briefing."
    ):
        raise ValueError("Manifest timing endpoint is invalid.")
    if require_finished and manifest.get("finish_tree_gate") != "passed":
        raise ValueError("Manifest finish-time source-tree gate did not pass.")

    trials = manifest.get("trials")
    if not isinstance(trials, list) or len(trials) != len(FIXED_SEEDS):
        raise ValueError("Manifest must contain exactly three trials.")
    databases: set[str] = set()
    redis_ports: set[int] = set()
    queues: set[str] = set()
    users: set[str] = set()
    storage_namespaces: set[str] = set()
    for index, (trial, seed) in enumerate(zip(trials, FIXED_SEEDS, strict=True), 1):
        trial_id = expected_trial_id(index)
        if (
            not isinstance(trial, dict)
            or trial.get("trial_id") != trial_id
            or trial.get("seed_arxiv_id") != seed
            or trial.get("measurement_invocations") != 1
            or trial.get("automatic_retry_performed") is not False
        ):
            raise ValueError(f"Manifest trial {index} violates the fixed protocol.")
        relative_dir = trial.get("relative_dir")
        if (
            not isinstance(relative_dir, str)
            or Path(relative_dir).is_absolute()
            or ".." in Path(relative_dir).parts
        ):
            raise ValueError(f"Manifest trial {index} has an unsafe relative path.")
        database = trial.get("database_name")
        if database != f"{run_id}_{trial_id}":
            raise ValueError(f"Manifest trial {index} has an invalid database.")
        redis_port = trial.get("redis_instance_port")
        if not isinstance(redis_port, int) or not 1024 <= redis_port <= 65535:
            raise ValueError(f"Manifest trial {index} has an invalid Redis port.")
        queue = trial.get("queue_name")
        if queue != f"mneme:jobs:eval:{run_id}:{trial_id}":
            raise ValueError(f"Manifest trial {index} has an invalid queue.")
        user = trial.get("disposable_user_id")
        try:
            normalized_user = str(UUID(str(user)))
        except ValueError as error:
            raise ValueError(f"Manifest trial {index} has an invalid disposable user.") from error
        storage_namespace = trial.get("storage_namespace")
        if storage_namespace != database:
            raise ValueError(f"Manifest trial {index} has invalid storage isolation.")
        databases.add(database)
        redis_ports.add(redis_port)
        queues.add(queue)
        users.add(normalized_user)
        storage_namespaces.add(str(storage_namespace))
    if not all(
        len(values) == len(FIXED_SEEDS)
        for values in (databases, redis_ports, queues, users, storage_namespaces)
    ):
        raise ValueError("Each seed trial must use distinct disposable state.")
    return trials


def read_measurement(path: Path, *, trial_id: str, seed: str) -> tuple[float, tuple[str, ...]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing Android measurement: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != EXPECTED_FIELDS:
            raise ValueError("Android measurement header is not the fixed schema.")
        rows = list(reader)
    if len(rows) != 1:
        raise ValueError("Android measurement must contain exactly one data row.")
    row = rows[0]
    expected = {
        "schema_version": "seed-first-initialization-android-v1",
        "trial_id": trial_id,
        "seed_arxiv_id": seed,
        "success": "true",
        "outcome": "live_five_paper_briefing_visible",
        "paper_count": str(EXPECTED_PAPER_COUNT),
        "content_origin": "LIVE_BACKEND",
    }
    for field, value in expected.items():
        if row.get(field) != value:
            raise ValueError(f"{trial_id} has {field}={row.get(field)!r}; expected {value!r}.")
    duration = float(row.get("duration_ms", ""))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError(f"{trial_id} duration must be finite and positive.")
    paper_ids = tuple(item for item in row.get("paper_ids", "").split(";") if item)
    if len(paper_ids) != EXPECTED_PAPER_COUNT or len(set(paper_ids)) != len(paper_ids):
        raise ValueError(f"{trial_id} must contain five unique paper IDs.")
    for paper_id in paper_ids:
        UUID(paper_id)
    return duration, paper_ids


def validate_precondition(
    payload: dict[str, Any], *, manifest: dict[str, Any], trial: dict[str, Any]
) -> None:
    expected = {
        "schema_version": "seed-first-initialization-precondition-v1",
        "run_id": manifest["run_id"],
        "trial_id": trial["trial_id"],
        "seed_arxiv_id": trial["seed_arxiv_id"],
        "database_name": trial["database_name"],
        "redis_instance_port": trial["redis_instance_port"],
        "queue_name": trial["queue_name"],
        "storage_namespace": trial["storage_namespace"],
        "disposable_user_id": trial["disposable_user_id"],
        "storage_file_count": 0,
        "redis_key_count": 0,
        "passed": True,
        "secrets_retained": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"{trial['trial_id']} precondition has invalid {field}.")
    counts = payload.get("database_counts")
    if (
        not isinstance(counts, dict)
        or counts.get("users") != 1
        or counts.get("user_preferences") != 1
        or any(counts.get(table) != 0 for table in EMPTY_DOMAIN_TABLES)
    ):
        raise ValueError(f"{trial['trial_id']} backend was not fresh before timing.")


def validate_backend_snapshot(
    payload: dict[str, Any],
    *,
    manifest: dict[str, Any],
    trial: dict[str, Any],
    paper_ids: tuple[str, ...],
) -> None:
    expected = {
        "schema_version": "seed-first-initialization-backend-snapshot-v1",
        "run_id": manifest["run_id"],
        "trial_id": trial["trial_id"],
        "seed_arxiv_id": trial["seed_arxiv_id"],
        "database_name": trial["database_name"],
        "redis_instance_port": trial["redis_instance_port"],
        "queue_name": trial["queue_name"],
        "storage_namespace": trial["storage_namespace"],
        "disposable_user_id": trial["disposable_user_id"],
        "paper_count": EXPECTED_PAPER_COUNT,
        "ordered_ui_paper_ids": list(paper_ids),
        "secrets_retained": False,
    }
    for field, value in expected.items():
        if payload.get(field) != value:
            raise ValueError(f"{trial['trial_id']} backend snapshot has invalid {field}.")
    ui_papers = payload.get("ui_papers")
    if not isinstance(ui_papers, list) or len(ui_papers) != EXPECTED_PAPER_COUNT:
        raise ValueError(f"{trial['trial_id']} snapshot lacks five UI papers.")
    if [item.get("paper_id") for item in ui_papers] != list(paper_ids):
        raise ValueError(f"{trial['trial_id']} backend order differs from Android.")
    if [item.get("rank") for item in ui_papers] != list(range(1, EXPECTED_PAPER_COUNT + 1)):
        raise ValueError(f"{trial['trial_id']} backend ranks are invalid.")
    if any(item.get("processing_status") not in {"ready", "partial"} for item in ui_papers):
        raise ValueError(f"{trial['trial_id']} contains an unusable UI paper.")
    checksum = payload.get("backend_snapshot_sha256")
    if not isinstance(checksum, str) or SHA256_PATTERN.fullmatch(checksum) is None:
        raise ValueError(f"{trial['trial_id']} snapshot checksum is invalid.")


def parse_candidate_source(path: Path, *, trial_id: str, seed: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing structured API log: {path}")
    structured: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            structured.append(payload)
    completions = [
        item
        for item in structured
        if item.get("event") == "seed_initialization_completed"
        and item.get("seed_arxiv_id") == seed
    ]
    if len(completions) != 1:
        raise ValueError(f"{trial_id} must have exactly one structured completion event.")
    completion = completions[0]
    source = completion.get("candidate_source")
    request_id = completion.get("request_id")
    if (
        source not in CANDIDATE_SOURCES
        or completion.get("paper_count") != EXPECTED_PAPER_COUNT
        or not isinstance(request_id, str)
        or not request_id
    ):
        raise ValueError(f"{trial_id} completion event is incomplete.")
    accesses = [
        item
        for item in structured
        if item.get("event") == "request_completed"
        and item.get("request_id") == request_id
        and item.get("http_method") == "POST"
        and item.get("http_path") == "/v1/onboarding/seed"
        and item.get("http_status") == 200
    ]
    if len(accesses) != 1:
        raise ValueError(f"{trial_id} lacks one matching successful onboarding access event.")
    api_duration = float(accesses[0].get("duration_ms"))
    if not math.isfinite(api_duration) or api_duration <= 0:
        raise ValueError(f"{trial_id} API request duration is invalid.")
    return {
        "schema_version": "seed-first-initialization-candidate-source-v1",
        "trial_id": trial_id,
        "seed_arxiv_id": seed,
        "candidate_source": source,
        "category": completion.get("category"),
        "paper_count": EXPECTED_PAPER_COUNT,
        "request_id": request_id,
        "api_request_duration_ms": api_duration,
        "source_event": "seed_initialization_completed",
        "secrets_retained": False,
    }


def validate_trial(run_dir: Path, trial_id: str, *, write_evidence: bool) -> TrialResult:
    manifest = read_json(run_dir / "run_manifest.json")
    trials = validate_manifest(manifest, require_finished=False)
    matching = [item for item in trials if item["trial_id"] == trial_id]
    if len(matching) != 1:
        raise ValueError(f"Unknown trial ID: {trial_id}")
    trial = matching[0]
    trial_dir = run_dir / trial["relative_dir"]
    duration, paper_ids = read_measurement(
        trial_dir / "android_measurement.csv",
        trial_id=trial_id,
        seed=trial["seed_arxiv_id"],
    )
    validate_precondition(
        read_json(trial_dir / "precondition.json"),
        manifest=manifest,
        trial=trial,
    )
    validate_backend_snapshot(
        read_json(trial_dir / "backend_snapshot.json"),
        manifest=manifest,
        trial=trial,
        paper_ids=paper_ids,
    )
    source = parse_candidate_source(
        trial_dir / "api_output.txt",
        trial_id=trial_id,
        seed=trial["seed_arxiv_id"],
    )
    result = TrialResult(
        trial_id=trial_id,
        seed_arxiv_id=trial["seed_arxiv_id"],
        duration_ms=duration,
        candidate_source=source["candidate_source"],
        api_request_duration_ms=source["api_request_duration_ms"],
        paper_count=EXPECTED_PAPER_COUNT,
        paper_ids=";".join(paper_ids),
    )
    if write_evidence:
        write_json(trial_dir / "candidate_source.json", source)
        write_json(
            trial_dir / "immediate_validation.json",
            {
                "schema_version": "seed-first-initialization-trial-validation-v1",
                "passed": True,
                **asdict(result),
            },
        )
    return result


def analyze(run_dir: Path) -> list[TrialResult]:
    manifest = read_json(run_dir / "run_manifest.json")
    trials = validate_manifest(manifest, require_finished=True)
    results = [validate_trial(run_dir, trial["trial_id"], write_evidence=False) for trial in trials]
    for trial, result in zip(trials, results, strict=True):
        validation = read_json(run_dir / trial["relative_dir"] / "immediate_validation.json")
        if validation != {
            "schema_version": "seed-first-initialization-trial-validation-v1",
            "passed": True,
            **asdict(result),
        }:
            raise ValueError(f"{trial['trial_id']} immediate validation evidence is stale.")
    return results


def write_results(output_dir: Path, results: list[TrialResult]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(result) for result in results]
    with (output_dir / "seed_results.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    values = [item.duration_ms for item in results]
    sources = [item.candidate_source for item in results]
    write_json(
        output_dir / "summary.json",
        {
            "schema_version": "seed-first-initialization-analysis-v1",
            "trial_count": len(results),
            "successful_trials": len(results),
            "all_trials_valid": True,
            "duration_ms": {
                "values": values,
                "median": statistics.median(values),
                "minimum": min(values),
                "maximum": max(values),
                "range": max(values) - min(values),
            },
            "candidate_sources": sources,
            "candidate_sources_homogeneous": len(set(sources)) == 1,
            "individual_results": rows,
            "interpretation_boundary": (
                "Three fixed, single first-initialization observations from submit "
                "click to a visible live five-paper briefing. Each trial used fresh "
                "Android data, PostgreSQL, Redis, storage, and user state. Host caches "
                "and live external-provider conditions were not reset. Candidate source "
                "is retained because citation-graph and category-fallback paths have "
                "different workloads. Descriptive median, minimum, maximum, and range "
                "only; no percentile, confidence interval, or population claim."
            ),
        },
    )


def _self_test_fixture(root: Path) -> Path:
    run_id = "mneme_eval_si_20260729t000000z_deadbeef"
    run_dir = root / run_id
    trials: list[dict[str, Any]] = []
    for index, seed in enumerate(FIXED_SEEDS, 1):
        trial_id = expected_trial_id(index)
        database = f"{run_id}_{trial_id}"
        user_id = f"00000000-0000-4000-8000-{index:012d}"
        trials.append(
            {
                "trial_id": trial_id,
                "seed_arxiv_id": seed,
                "relative_dir": f"trials/{trial_id}_{seed.replace('.', '_')}",
                "database_name": database,
                "redis_instance_port": 6400 + index,
                "queue_name": f"mneme:jobs:eval:{run_id}:{trial_id}",
                "storage_namespace": database,
                "disposable_user_id": user_id,
                "measurement_invocations": 1,
                "automatic_retry_performed": False,
            }
        )
    write_json(
        run_dir / "run_manifest.json",
        {
            "schema_version": "seed-first-initialization-run-manifest-v1",
            "run_id": run_id,
            "repository_revision": "a" * 40,
            "fixed_seeds": list(FIXED_SEEDS),
            "timing_endpoint": (
                "Immediately before submit click to visible live five-paper briefing."
            ),
            "one_measurement_per_seed": True,
            "automatic_experiment_retry_enabled": False,
            "android_data_cleared_before_each_trial": True,
            "fresh_database_per_trial": True,
            "fresh_redis_per_trial": True,
            "fresh_storage_per_trial": True,
            "fresh_user_per_trial": True,
            "source_tree_clean_at_start": True,
            "token_retained": False,
            "finish_tree_gate": "passed",
            "trials": trials,
        },
    )
    fields = ",".join(EXPECTED_FIELDS)
    for index, trial in enumerate(trials, 1):
        trial_dir = run_dir / trial["relative_dir"]
        paper_ids = [f"10000000-0000-4000-8000-{index * 10 + item:012d}" for item in range(1, 6)]
        trial_dir.mkdir(parents=True)
        (trial_dir / "android_measurement.csv").write_text(
            fields
            + "\n"
            + ",".join(
                [
                    "seed-first-initialization-android-v1",
                    trial["trial_id"],
                    trial["seed_arxiv_id"],
                    str(index * 1000.0),
                    "true",
                    "live_five_paper_briefing_visible",
                    "5",
                    ";".join(paper_ids),
                    "LIVE_BACKEND",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        counts = {table: 0 for table in EMPTY_DOMAIN_TABLES}
        counts.update({"users": 1, "user_preferences": 1})
        write_json(
            trial_dir / "precondition.json",
            {
                "schema_version": "seed-first-initialization-precondition-v1",
                "run_id": run_id,
                "trial_id": trial["trial_id"],
                "seed_arxiv_id": trial["seed_arxiv_id"],
                "database_name": trial["database_name"],
                "redis_instance_port": trial["redis_instance_port"],
                "queue_name": trial["queue_name"],
                "storage_namespace": trial["storage_namespace"],
                "disposable_user_id": trial["disposable_user_id"],
                "database_counts": counts,
                "storage_file_count": 0,
                "redis_key_count": 0,
                "passed": True,
                "secrets_retained": False,
            },
        )
        write_json(
            trial_dir / "backend_snapshot.json",
            {
                "schema_version": "seed-first-initialization-backend-snapshot-v1",
                "run_id": run_id,
                "trial_id": trial["trial_id"],
                "seed_arxiv_id": trial["seed_arxiv_id"],
                "database_name": trial["database_name"],
                "redis_instance_port": trial["redis_instance_port"],
                "queue_name": trial["queue_name"],
                "storage_namespace": trial["storage_namespace"],
                "disposable_user_id": trial["disposable_user_id"],
                "paper_count": 5,
                "ordered_ui_paper_ids": paper_ids,
                "ui_papers": [
                    {
                        "paper_id": paper_id,
                        "rank": rank,
                        "processing_status": "ready",
                    }
                    for rank, paper_id in enumerate(paper_ids, 1)
                ],
                "backend_snapshot_sha256": "b" * 64,
                "secrets_retained": False,
            },
        )
        request_id = f"request-{index}"
        structured = [
            {
                "event": "seed_initialization_completed",
                "request_id": request_id,
                "seed_arxiv_id": trial["seed_arxiv_id"],
                "candidate_source": "citation_graph",
                "category": "cs.AI",
                "paper_count": 5,
            },
            {
                "event": "request_completed",
                "request_id": request_id,
                "http_method": "POST",
                "http_path": "/v1/onboarding/seed",
                "http_status": 200,
                "duration_ms": index * 900.0,
            },
        ]
        (trial_dir / "api_output.txt").write_text(
            "uvicorn startup\n"
            + "\n".join(json.dumps(item, sort_keys=True) for item in structured)
            + "\n",
            encoding="utf-8",
        )
        validate_trial(run_dir, trial["trial_id"], write_evidence=True)
    return run_dir


def run_self_test() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        run_dir = _self_test_fixture(Path(temporary))
        results = analyze(run_dir)
        if [item.duration_ms for item in results] != [1000.0, 2000.0, 3000.0]:
            raise AssertionError("Self-test valid fixture produced wrong results.")
        write_results(run_dir / "analysis", results)
        summary = read_json(run_dir / "analysis" / "summary.json")
        if summary["duration_ms"] != {
            "values": [1000.0, 2000.0, 3000.0],
            "median": 2000.0,
            "minimum": 1000.0,
            "maximum": 3000.0,
            "range": 2000.0,
        }:
            raise AssertionError("Self-test summary statistics are incorrect.")
        measurement = run_dir / "trials/trial_01_1706_03762/android_measurement.csv"
        original = measurement.read_text(encoding="utf-8")
        measurement.write_text(original.replace("1000.0", "nan"), encoding="utf-8")
        try:
            validate_trial(run_dir, "trial_01", write_evidence=False)
        except ValueError as error:
            if "finite and positive" not in str(error):
                raise
        else:
            raise AssertionError("Self-test accepted a non-finite duration.")
    print("seed first-initialization analyzer self-test: PASS")


def main() -> None:
    arguments = parse_arguments()
    if arguments.command == "self-test":
        run_self_test()
        return
    run_dir = arguments.run_dir.resolve()
    if arguments.command == "validate-trial":
        trial_dir: Path | None = None
        try:
            manifest = read_json(run_dir / "run_manifest.json")
            trials = validate_manifest(manifest, require_finished=False)
            matching = [item for item in trials if item["trial_id"] == arguments.trial_id]
            if len(matching) == 1:
                trial_dir = run_dir / matching[0]["relative_dir"]
            result = validate_trial(run_dir, arguments.trial_id, write_evidence=True)
        except Exception as error:
            if trial_dir is not None:
                write_json(
                    trial_dir / "immediate_validation.json",
                    {
                        "schema_version": ("seed-first-initialization-trial-validation-v1"),
                        "passed": False,
                        "error_type": type(error).__name__,
                        "error": str(error),
                    },
                )
            raise
        print(json.dumps({"status": "ok", **asdict(result)}, sort_keys=True))
        return
    results = analyze(run_dir)
    output_dir = (arguments.output_dir or run_dir / "analysis").resolve()
    write_results(output_dir, results)
    print(
        json.dumps(
            {"status": "ok", "trial_count": len(results), "output": str(output_dir)},
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
