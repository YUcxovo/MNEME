#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "matplotlib==3.10.3",
# ]
# ///
"""Validate and summarize the formal Android event-synchronization experiment."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

EXPECTED_ITERATIONS = 10
EVENT_COUNT = 3
EXPECTED_HEADER = (
    "track",
    "scenario",
    "iteration",
    "event_count",
    "duration_ms",
    "success",
    "outcome",
    "accepted",
    "duplicates",
    "final_state",
    "event_ids",
)


@dataclass(frozen=True)
class Scenario:
    key: str
    label: str
    outcome: str
    accepted: str
    duplicates: str
    final_state: str


SCENARIOS = (
    Scenario(
        "file_room_queue_write",
        "Queue write",
        "three_events_written",
        "",
        "",
        "pending:3",
    ),
    Scenario(
        "file_room_reopen_pending",
        "Room reopen",
        "pending_events_restored",
        "",
        "",
        "pending:3",
    ),
    Scenario(
        "http_503_pending_recovery",
        "HTTP 503",
        "retry_api_503",
        "",
        "",
        "pending:3",
    ),
    Scenario(
        "live_backend_upload",
        "Live upload",
        "synced_3_3_0",
        "3",
        "0",
        "synced:3",
    ),
    Scenario(
        "live_backend_duplicate_replay",
        "Duplicate replay",
        "synced_3_0_3",
        "0",
        "3",
        "synced:3",
    ),
)
SCENARIO_BY_KEY = {scenario.key: scenario for scenario in SCENARIOS}


@dataclass(frozen=True)
class Measurement:
    raw_order: int
    scenario: str
    iteration: int
    duration_ms: float
    event_ids: tuple[str, ...]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        rows = list(reader)
    return header, rows


def require_canonical_integer(value: str, *, field: str, row_number: int) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"Row {row_number}: {field} is not an integer.") from error
    if str(parsed) != value:
        raise ValueError(f"Row {row_number}: {field} is not canonical.")
    return parsed


def parse_event_ids(value: str, *, row_number: int) -> tuple[str, ...]:
    values = tuple(value.split("+"))
    if len(values) != EVENT_COUNT or len(set(values)) != EVENT_COUNT:
        raise ValueError(
            f"Row {row_number}: event_ids must contain three distinct UUIDs."
        )
    for event_id in values:
        try:
            uuid.UUID(event_id)
        except ValueError as error:
            raise ValueError(f"Row {row_number}: invalid event UUID.") from error
    return values


def validate_rows(
    header: list[str],
    rows: list[dict[str, str]],
) -> list[Measurement]:
    if tuple(header) != EXPECTED_HEADER:
        raise ValueError(
            f"Unexpected CSV header.\nExpected: {EXPECTED_HEADER}\nObserved: {tuple(header)}",
        )
    expected_order = [
        (iteration, scenario.key)
        for iteration in range(1, EXPECTED_ITERATIONS + 1)
        for scenario in SCENARIOS
    ]
    if len(rows) != len(expected_order):
        raise ValueError(
            f"Expected exactly {len(expected_order)} measurements; observed {len(rows)}.",
        )

    observed_order: list[tuple[int, str]] = []
    measurements: list[Measurement] = []
    ids_by_iteration: dict[int, tuple[str, ...]] = {}
    all_event_ids: set[str] = set()

    for raw_order, row in enumerate(rows, start=1):
        if None in row:
            raise ValueError(
                f"Row {raw_order}: extra unlabelled CSV values were found."
            )
        scenario_key = row["scenario"]
        if scenario_key not in SCENARIO_BY_KEY:
            raise ValueError(f"Row {raw_order}: unexpected scenario {scenario_key!r}.")
        scenario = SCENARIO_BY_KEY[scenario_key]
        iteration = require_canonical_integer(
            row["iteration"],
            field="iteration",
            row_number=raw_order,
        )
        event_count = require_canonical_integer(
            row["event_count"],
            field="event_count",
            row_number=raw_order,
        )
        if event_count != EVENT_COUNT:
            raise ValueError(f"Row {raw_order}: event_count must be {EVENT_COUNT}.")
        if row["track"] != "event_sync_formal":
            raise ValueError(f"Row {raw_order}: unexpected track.")
        if row["success"] != "true":
            raise ValueError(f"Row {raw_order}: success must be the literal true.")
        if row["outcome"] != scenario.outcome:
            raise ValueError(f"Row {raw_order}: incorrect outcome for {scenario_key}.")
        if row["accepted"] != scenario.accepted:
            raise ValueError(
                f"Row {raw_order}: incorrect accepted count for {scenario_key}."
            )
        if row["duplicates"] != scenario.duplicates:
            raise ValueError(
                f"Row {raw_order}: incorrect duplicate count for {scenario_key}.",
            )
        if row["final_state"] != scenario.final_state:
            raise ValueError(
                f"Row {raw_order}: incorrect final state for {scenario_key}."
            )

        try:
            duration_ms = float(row["duration_ms"])
        except ValueError as error:
            raise ValueError(f"Row {raw_order}: duration_ms is not numeric.") from error
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError(
                f"Row {raw_order}: duration_ms must be finite and non-negative."
            )

        event_ids = parse_event_ids(row["event_ids"], row_number=raw_order)
        if iteration in ids_by_iteration:
            if ids_by_iteration[iteration] != event_ids:
                raise ValueError(
                    f"Row {raw_order}: event IDs changed within iteration {iteration}.",
                )
        else:
            overlapping = all_event_ids.intersection(event_ids)
            if overlapping:
                raise ValueError(
                    f"Row {raw_order}: event IDs were reused across iterations.",
                )
            ids_by_iteration[iteration] = event_ids
            all_event_ids.update(event_ids)

        observed_order.append((iteration, scenario_key))
        measurements.append(
            Measurement(
                raw_order=raw_order,
                scenario=scenario_key,
                iteration=iteration,
                duration_ms=duration_ms,
                event_ids=event_ids,
            ),
        )

    if observed_order != expected_order:
        raise ValueError(
            "Rows must contain one complete five-stage batch for iterations 1 through 10 "
            "in acquisition order; missing, duplicate, or reordered iterations were found.",
        )
    return measurements


def require_sha256(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64:
        raise ValueError(f"Manifest field {field} is not a SHA-256 digest.")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"Manifest field {field} is not a SHA-256 digest.") from error
    return value


def reject_sensitive_manifest_keys(value: Any, *, path: str = "manifest") -> None:
    forbidden_fragments = ("token", "secret", "authorization", "credential")
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower()
            if any(fragment in normalized for fragment in forbidden_fragments):
                raise ValueError(f"Sensitive manifest key is forbidden: {path}.{key}")
            reject_sensitive_manifest_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_sensitive_manifest_keys(child, path=f"{path}[{index}]")


def android_code_listing(repository_root: Path, revision: str) -> bytes:
    return subprocess.run(
        [
            "git",
            "-C",
            str(repository_root),
            "ls-tree",
            "-r",
            "--full-tree",
            revision,
            "android/app/src",
            "android/app/build.gradle.kts",
            "android/gradle/libs.versions.toml",
        ],
        check=True,
        capture_output=True,
    ).stdout


def validate_manifest(run_dir: Path, manifest: dict[str, Any], raw_csv: Path) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    reject_sensitive_manifest_keys(manifest)
    if manifest.get("schema_version") != "android-formal-event-sync-run-v1":
        raise ValueError("Unexpected run-manifest schema.")
    if manifest.get("mode") != "formal":
        raise ValueError("Only a formal run may be summarized.")
    if manifest.get("requested_iterations") != EXPECTED_ITERATIONS:
        raise ValueError("The formal manifest must request exactly 10 iterations.")

    execution = manifest.get("execution")
    if not isinstance(execution, dict):
        raise TypeError("The manifest execution section is missing.")
    required_execution = {
        "instrumentation_invocations": 1,
        "shell_exit_status": 0,
        "instrumentation_exit_status": 0,
        "instrumentation_reported_success": True,
        "data_pull_exit_status": 0,
    }
    for key, expected in required_execution.items():
        if execution.get(key) != expected:
            raise ValueError(f"Manifest execution.{key} must equal {expected!r}.")

    build = manifest.get("build")
    if not isinstance(build, dict) or build.get("build_authentication") != "blank":
        raise ValueError(
            "The app must have been built with blank build-time authentication."
        )

    repository = manifest.get("repository")
    if not isinstance(repository, dict):
        raise TypeError("The repository provenance is missing.")
    revision = repository.get("revision")
    tree = repository.get("tree")
    if not isinstance(revision, str) or len(revision) != 40:
        raise ValueError("The repository revision is invalid.")
    if not isinstance(tree, str) or len(tree) != 40:
        raise ValueError("The repository tree is invalid.")
    observed_tree = subprocess.run(
        ["git", "-C", str(repository_root), "rev-parse", f"{revision}^{{tree}}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if observed_tree != tree:
        raise ValueError("The recorded repository tree does not match the revision.")
    if repository.get("clean_at_start") is not True:
        raise ValueError("The measurement did not start from a clean revision.")
    if repository.get("unchanged_at_finish") is not True:
        raise ValueError("The measured source tree changed during acquisition.")

    backend = manifest.get("backend")
    if (
        not isinstance(backend, dict)
        or backend.get("isolated_test_instance_acknowledged") is not True
    ):
        raise ValueError("An isolated test backend was not acknowledged.")

    android = manifest.get("android")
    host = manifest.get("host")
    if not isinstance(android, dict) or not isinstance(host, dict):
        raise TypeError("Manifest device and host provenance is incomplete.")
    required_app_data_guards = {
        "disposable_measurement_app_data": True,
        "force_stopped_before_clear": True,
        "app_data_cleared_before_instrumentation": True,
    }
    for field, expected in required_app_data_guards.items():
        if android.get(field) is not expected:
            raise ValueError(f"Manifest android.{field} must be true.")
    for field in ("serial", "api", "model", "webview_version", "boot_id"):
        if android.get(field) in (None, ""):
            raise ValueError(f"Manifest android.{field} is missing.")
    if host.get("loadavg") in (None, ""):
        raise ValueError("Manifest host.loadavg is missing.")

    hashes = manifest.get("hashes")
    if not isinstance(hashes, dict):
        raise TypeError("The manifest hash section is missing.")
    hash_fields = (
        "runner_sha256",
        "analyzer_sha256",
        "measured_test_source_sha256",
        "android_code_tree_sha256",
        "application_apk_sha256",
        "instrumentation_apk_sha256",
        "raw_csv_sha256",
        "device_test_environment_sha256",
        "instrumentation_output_sha256",
        "build_output_sha256",
        "install_output_sha256",
        "environment_sha256",
        "adb_pull_output_sha256",
    )
    for field in hash_fields:
        require_sha256(hashes.get(field), field=f"hashes.{field}")

    if (
        hashlib.sha256(android_code_listing(repository_root, revision)).hexdigest()
        != hashes["android_code_tree_sha256"]
    ):
        raise ValueError("The Android code-tree digest does not match the revision.")

    current_files = {
        "runner_sha256": (
            repository_root / "tools/evaluation/run_android_formal_event_sync.sh"
        ),
        "analyzer_sha256": Path(__file__).resolve(),
        "measured_test_source_sha256": (
            repository_root
            / "android/app/src/androidTest/java/com/mneme/app/evaluation/"
            "E4LiveBackendClosedLoopTest.kt"
        ),
        "raw_csv_sha256": raw_csv,
        "device_test_environment_sha256": run_dir / "device_test_environment.json",
        "instrumentation_output_sha256": run_dir / "instrumentation_output.txt",
        "build_output_sha256": run_dir / "build_output.txt",
        "install_output_sha256": run_dir / "install_output.txt",
        "environment_sha256": run_dir / "environment.json",
        "adb_pull_output_sha256": run_dir / "adb_pull_output.txt",
    }
    for field, path in current_files.items():
        if not path.is_file():
            raise FileNotFoundError(f"Manifest artifact is missing: {path}")
        if sha256(path) != hashes[field]:
            raise ValueError(f"SHA-256 mismatch for {path}.")

    environment = run_dir / "environment.json"
    if not environment.is_file():
        raise FileNotFoundError(f"Runner environment is missing: {environment}")
    environment_payload = json.loads(environment.read_text(encoding="utf-8"))
    emulator = environment_payload.get("emulator")
    host = environment_payload.get("host")
    if not isinstance(emulator, dict) or not isinstance(host, dict):
        raise TypeError("Environment provenance is incomplete.")
    for field in ("serial", "android_api", "model", "webview_version", "boot_id"):
        if emulator.get(field) in (None, ""):
            raise ValueError(f"Environment emulator.{field} is missing.")
    if host.get("loadavg") in (None, ""):
        raise ValueError("Environment host.loadavg is missing.")


def write_validated_raw(
    output_path: Path,
    rows: list[dict[str, str]],
) -> None:
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("raw_order", *EXPECTED_HEADER))
        for raw_order, row in enumerate(rows, start=1):
            writer.writerow((raw_order, *(row[field] for field in EXPECTED_HEADER)))


def summarize(measurements: list[Measurement]) -> list[dict[str, str | int | float]]:
    summaries: list[dict[str, str | int | float]] = []
    for scenario in SCENARIOS:
        values = [
            measurement.duration_ms
            for measurement in measurements
            if measurement.scenario == scenario.key
        ]
        minimum = min(values)
        maximum = max(values)
        summaries.append(
            {
                "scenario": scenario.key,
                "label": scenario.label,
                "sample_count": len(values),
                "success_count": len(values),
                "median_ms": round(statistics.median(values), 2),
                "min_ms": round(minimum, 2),
                "max_ms": round(maximum, 2),
                "range_ms": round(maximum - minimum, 2),
            },
        )
    return summaries


def write_summary_csv(
    output_path: Path,
    summaries: list[dict[str, str | int | float]],
) -> None:
    fieldnames = (
        "scenario",
        "label",
        "sample_count",
        "success_count",
        "median_ms",
        "min_ms",
        "max_ms",
        "range_ms",
    )
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(summaries)


def plot_measurements(
    output_path: Path,
    measurements: list[Measurement],
) -> None:
    figure, axis = plt.subplots(figsize=(9.2, 4.8))
    for position, scenario in enumerate(SCENARIOS, start=1):
        values = [
            measurement.duration_ms
            for measurement in measurements
            if measurement.scenario == scenario.key
        ]
        offsets = [position - 0.18 + 0.04 * index for index in range(len(values))]
        axis.scatter(
            offsets,
            values,
            s=27,
            color="#2364AA",
            alpha=0.78,
            edgecolors="white",
            linewidths=0.45,
            zorder=2,
        )
        median = statistics.median(values)
        axis.plot(
            [position - 0.25, position + 0.25],
            [median, median],
            color="#C73E1D",
            linewidth=2.2,
            zorder=3,
        )
    axis.set_xticks(
        range(1, len(SCENARIOS) + 1),
        [scenario.label for scenario in SCENARIOS],
    )
    axis.set_ylabel("Latency (ms)")
    axis.set_title("Formal Android event-sync latency (10 batches)")
    axis.grid(axis="y", color="#D7DCE2", linewidth=0.7)
    axis.set_axisbelow(True)
    axis.spines[["top", "right"]].set_visible(False)
    figure.tight_layout()
    figure.savefig(output_path, dpi=220)
    plt.close(figure)


def analyze(run_dir: Path) -> None:
    run_dir = run_dir.resolve()
    raw_csv = run_dir / "formal_event_sync_measurements.csv"
    manifest_path = run_dir / "run_manifest.json"
    if not raw_csv.is_file():
        raise FileNotFoundError(f"Formal event-sync CSV is missing: {raw_csv}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Run manifest is missing: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    validate_manifest(run_dir, manifest, raw_csv)
    header, rows = read_csv(raw_csv)
    measurements = validate_rows(header, rows)
    summaries = summarize(measurements)

    analysis_dir = run_dir / "analysis"
    if analysis_dir.exists():
        raise FileExistsError(
            f"Analysis output already exists and will not be overwritten: {analysis_dir}",
        )
    analysis_dir.mkdir()
    write_validated_raw(analysis_dir / "validated_raw_order.csv", rows)
    write_summary_csv(analysis_dir / "summary.csv", summaries)
    (analysis_dir / "summary.json").write_text(
        json.dumps(
            {
                "schema_version": "android-formal-event-sync-summary-v1",
                "run_id": manifest["run_id"],
                "repository_revision": manifest["repository"]["revision"],
                "raw_csv_sha256": manifest["hashes"]["raw_csv_sha256"],
                "descriptive_statistics_only": True,
                "summaries": summaries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    plot_measurements(analysis_dir / "event_sync_latency.png", measurements)
    print(f"Validated 50 rows from 10 complete batches: {raw_csv}")
    print(f"Descriptive outputs written without retry or row removal: {analysis_dir}")


def synthetic_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for iteration in range(1, EXPECTED_ITERATIONS + 1):
        event_ids = "+".join(
            str(uuid.UUID(int=(iteration - 1) * EVENT_COUNT + offset + 1))
            for offset in range(EVENT_COUNT)
        )
        for scenario_index, scenario in enumerate(SCENARIOS):
            rows.append(
                {
                    "track": "event_sync_formal",
                    "scenario": scenario.key,
                    "iteration": str(iteration),
                    "event_count": str(EVENT_COUNT),
                    "duration_ms": f"{iteration + scenario_index / 10:.3f}",
                    "success": "true",
                    "outcome": scenario.outcome,
                    "accepted": scenario.accepted,
                    "duplicates": scenario.duplicates,
                    "final_state": scenario.final_state,
                    "event_ids": event_ids,
                },
            )
    return rows


def self_test() -> None:
    rows = synthetic_rows()
    measurements = validate_rows(list(EXPECTED_HEADER), rows)
    assert len(measurements) == 50
    assert [summary["sample_count"] for summary in summarize(measurements)] == [10] * 5

    mutations = []
    missing = [dict(row) for row in rows[:-1]]
    mutations.append(missing)
    duplicate_iteration = [dict(row) for row in rows]
    duplicate_iteration[5]["iteration"] = "1"
    mutations.append(duplicate_iteration)
    failed = [dict(row) for row in rows]
    failed[0]["success"] = "false"
    mutations.append(failed)
    wrong_event_count = [dict(row) for row in rows]
    wrong_event_count[0]["event_count"] = "2"
    mutations.append(wrong_event_count)
    wrong_accepted = [dict(row) for row in rows]
    wrong_accepted[-2]["accepted"] = "2"
    mutations.append(wrong_accepted)
    wrong_counts = [dict(row) for row in rows]
    wrong_counts[-1]["duplicates"] = "2"
    mutations.append(wrong_counts)
    wrong_state = [dict(row) for row in rows]
    wrong_state[2]["final_state"] = "synced:3"
    mutations.append(wrong_state)
    reused_ids = [dict(row) for row in rows]
    reused_ids[5]["event_ids"] = rows[0]["event_ids"]
    mutations.append(reused_ids)

    for mutation in mutations:
        try:
            validate_rows(list(EXPECTED_HEADER), mutation)
        except ValueError:
            continue
        raise AssertionError("A deliberately invalid synthetic fixture was accepted.")

    with tempfile.TemporaryDirectory() as directory:
        run_dir = Path(directory)
        raw_csv = run_dir / "formal_event_sync_measurements.csv"
        with raw_csv.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPECTED_HEADER)
            writer.writeheader()
            writer.writerows(rows)

        fixture_files = {
            "device_test_environment.json": '{"schema_version":"fixture"}\n',
            "instrumentation_output.txt": "OK (1 test)\n",
            "build_output.txt": "synthetic build\n",
            "install_output.txt": "synthetic install\n",
            "adb_pull_output.txt": "synthetic pull\n",
        }
        for file_name, payload in fixture_files.items():
            (run_dir / file_name).write_text(payload, encoding="utf-8")
        (run_dir / "environment.json").write_text(
            json.dumps(
                {
                    "emulator": {
                        "serial": "emulator-fixture",
                        "android_api": 34,
                        "model": "fixture",
                        "webview_version": "1.0",
                        "boot_id": "fixture-boot",
                    },
                    "host": {"loadavg": "0.1 0.1 0.1 1/1 1"},
                },
            )
            + "\n",
            encoding="utf-8",
        )

        repository_root = Path(__file__).resolve().parents[2]
        revision = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        tree = subprocess.run(
            ["git", "-C", str(repository_root), "rev-parse", "HEAD^{tree}"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        hashes = {
            "runner_sha256": sha256(
                repository_root / "tools/evaluation/run_android_formal_event_sync.sh"
            ),
            "analyzer_sha256": sha256(Path(__file__).resolve()),
            "measured_test_source_sha256": sha256(
                repository_root
                / "android/app/src/androidTest/java/com/mneme/app/evaluation/"
                "E4LiveBackendClosedLoopTest.kt"
            ),
            "android_code_tree_sha256": hashlib.sha256(
                android_code_listing(repository_root, revision),
            ).hexdigest(),
            "application_apk_sha256": "a" * 64,
            "instrumentation_apk_sha256": "b" * 64,
            "raw_csv_sha256": sha256(raw_csv),
            "device_test_environment_sha256": sha256(
                run_dir / "device_test_environment.json"
            ),
            "instrumentation_output_sha256": sha256(
                run_dir / "instrumentation_output.txt"
            ),
            "build_output_sha256": sha256(run_dir / "build_output.txt"),
            "install_output_sha256": sha256(run_dir / "install_output.txt"),
            "environment_sha256": sha256(run_dir / "environment.json"),
            "adb_pull_output_sha256": sha256(run_dir / "adb_pull_output.txt"),
        }
        manifest = {
            "schema_version": "android-formal-event-sync-run-v1",
            "run_id": "synthetic-formal-run",
            "mode": "formal",
            "requested_iterations": 10,
            "repository": {
                "revision": revision,
                "tree": tree,
                "clean_at_start": True,
                "unchanged_at_finish": True,
            },
            "backend": {"isolated_test_instance_acknowledged": True},
            "android": {
                "serial": "emulator-fixture",
                "api": 34,
                "model": "fixture",
                "webview_version": "1.0",
                "boot_id": "fixture-boot",
                "disposable_measurement_app_data": True,
                "force_stopped_before_clear": True,
                "app_data_cleared_before_instrumentation": True,
            },
            "host": {"loadavg": "0.1 0.1 0.1 1/1 1"},
            "execution": {
                "instrumentation_invocations": 1,
                "shell_exit_status": 0,
                "instrumentation_exit_status": 0,
                "instrumentation_reported_success": True,
                "data_pull_exit_status": 0,
            },
            "build": {"build_authentication": "blank"},
            "hashes": hashes,
        }
        (run_dir / "run_manifest.json").write_text(
            json.dumps(manifest) + "\n",
            encoding="utf-8",
        )
        analyze(run_dir)
        summary_output = run_dir / "analysis/summary.csv"
        if len(summary_output.read_text(encoding="utf-8").splitlines()) != 6:
            raise AssertionError("Synthetic summary did not contain five scenarios.")
    print("Synthetic formal event-sync analyzer self-test passed.")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir",
        nargs="?",
        type=Path,
        help="Raw formal run directory produced by the paired runner.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Validate synthetic accepted and rejected fixtures without reading a real run.",
    )
    arguments = parser.parse_args()
    if arguments.self_test == (arguments.run_dir is not None):
        parser.error("Provide exactly one of RUN_DIR or --self-test.")
    return arguments


def main() -> None:
    arguments = parse_arguments()
    if arguments.self_test:
        self_test()
        return
    analyze(arguments.run_dir)


if __name__ == "__main__":
    main()
