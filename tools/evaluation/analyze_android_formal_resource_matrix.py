#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "matplotlib==3.10.3",
# ]
# ///
"""Extract, validate, and summarize the formal Android resource matrix.

The formal analysis unit is one wiped-data emulator session. Five retained
measurements within a session are reduced to one session median. The two
session medians in each resource cell remain visible in every derived table;
this script deliberately does not calculate p95, confidence intervals,
significance tests, or population-level estimates.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

CONFIGS = {
    "cpu2_ram2gb": (2, 2048),
    "cpu2_ram6gb": (2, 6144),
    "cpu4_ram2gb": (4, 2048),
    "cpu4_ram6gb": (4, 6144),
}
CONFIG_LABELS = {
    "cpu2_ram2gb": "2 cores / 2 GiB",
    "cpu2_ram6gb": "2 cores / 6 GiB",
    "cpu4_ram2gb": "4 cores / 2 GiB",
    "cpu4_ram6gb": "4 cores / 6 GiB",
}
BLOCK_ORDERS = {
    1: (
        "cpu2_ram2gb",
        "cpu2_ram6gb",
        "cpu4_ram6gb",
        "cpu4_ram2gb",
    ),
    2: (
        "cpu4_ram2gb",
        "cpu4_ram6gb",
        "cpu2_ram6gb",
        "cpu2_ram2gb",
    ),
}
NODE_ORDERS = {
    1: (1, 12, 25, 50),
    2: (50, 25, 12, 1),
}
EDGE_COUNTS = {1: 0, 12: 16, 25: 36, 50: 73}
GRAPH_PHASES = ("new_webview_instance", "reused_webview")
STARTUP_SCENARIOS = ("cached_cold", "foreground_resume")
EXPECTED_STARTUP_METRICS = {
    "cached_cold": "timeToFullDisplayMs",
    "foreground_resume": "timeToInitialDisplayMs",
}
RESUME_CONTRACT_FILE = "MnemeStartupBenchmark_foregroundResume_contract.json"
EXPECTED_CACHED_UI_TAG = "briefing-content-5-cached-backend"
EXPECTED_RETAINED_ITERATIONS = tuple(range(1, 6))
EXPECTED_RAW_ITERATIONS = tuple(range(2, 7))


@dataclass(frozen=True)
class SessionSummary:
    session_id: str
    block: int
    sequence_position: int
    config_id: str
    cpu_cores: int
    ram_mb: int
    boot_id: str
    cached_cold_ms: float
    foreground_resume_ms: float
    graph_new_1_ms: float
    graph_new_12_ms: float
    graph_new_25_ms: float
    graph_new_50_ms: float
    graph_reused_1_ms: float
    graph_reused_12_ms: float
    graph_reused_25_ms: float
    graph_reused_50_ms: float


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object.")
    return payload


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: Sequence[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError(f"Refusing to write an empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def as_bool(value: str, *, source: Path) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{source} contains an invalid boolean: {value!r}")
    return normalized == "true"


def positive_float(value: str, *, source: Path) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise ValueError(f"{source} contains a non-positive duration: {value!r}")
    return parsed


def positive_int(value: str, *, source: Path, allow_zero: bool = False) -> int:
    parsed = int(value)
    lower_bound = 0 if allow_zero else 1
    if parsed < lower_bound:
        raise ValueError(f"{source} contains an invalid integer: {value!r}")
    return parsed


def rounded(value: float) -> float:
    return round(value, 3)


def normalize_name(value: str) -> str:
    return "".join(character.lower() for character in value if character.isalnum())


def benchmark_identifier(benchmark: dict[str, Any]) -> str:
    pieces = [
        str(benchmark.get("className", "")),
        str(benchmark.get("name", "")),
        str(benchmark.get("testName", "")),
        json.dumps(benchmark.get("params", {}), sort_keys=True),
    ]
    return " ".join(pieces)


def classify_startup_scenario(benchmark: dict[str, Any]) -> str | None:
    identifier = normalize_name(benchmark_identifier(benchmark))
    if "cold" in identifier:
        return "cached_cold"
    if "foreground" in identifier or "resume" in identifier:
        return "foreground_resume"
    return None


def numeric_runs(metric: Any, *, description: str) -> list[float]:
    if not isinstance(metric, dict):
        raise TypeError(f"{description} is not a metric object.")
    raw_runs = metric.get("runs")
    if not isinstance(raw_runs, list):
        raise TypeError(f"{description} does not contain a runs array.")
    values: list[float] = []
    for index, raw_value in enumerate(raw_runs, start=1):
        value: Any = raw_value
        if isinstance(raw_value, dict):
            for key in ("value", "valueMs", "durationMs", "median"):
                if key in raw_value:
                    value = raw_value[key]
                    break
        if not isinstance(value, (int, float)):
            raise TypeError(
                f"{description} run {index} is not numeric: {raw_value!r}",
            )
        parsed = float(value)
        if not math.isfinite(parsed) or parsed <= 0:
            raise ValueError(
                f"{description} run {index} is not a positive finite duration.",
            )
        values.append(parsed)
    return values


def select_metric(
    benchmark: dict[str, Any],
    *,
    scenario: str,
    requested_name: str | None,
) -> tuple[str, list[float]]:
    metrics = benchmark.get("metrics")
    if not isinstance(metrics, dict):
        raise TypeError(
            f"{benchmark_identifier(benchmark)} does not contain a metrics object.",
        )
    expected_name = EXPECTED_STARTUP_METRICS[scenario]
    if requested_name:
        if requested_name != expected_name:
            raise ValueError(
                f"The formal protocol requires {expected_name!r} for {scenario}; "
                f"received {requested_name!r}.",
            )
        exact = metrics.get(requested_name)
        if exact is None:
            available = ", ".join(sorted(str(key) for key in metrics))
            raise ValueError(
                f"Requested metric {requested_name!r} is absent from "
                f"{benchmark_identifier(benchmark)}; available: {available}",
            )
        return requested_name, numeric_runs(
            exact,
            description=f"{benchmark_identifier(benchmark)} / {requested_name}",
        )

    if expected_name in metrics:
        return expected_name, numeric_runs(
            metrics[expected_name],
            description=f"{benchmark_identifier(benchmark)} / {expected_name}",
        )
    available = ", ".join(sorted(str(key) for key in metrics))
    raise ValueError(
        f"{benchmark_identifier(benchmark)} does not contain the protocol metric "
        f"{expected_name!r} for {scenario}; available: {available}.",
    )


def iter_benchmarks(directory: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    paths = sorted(directory.rglob("*-benchmarkData.json"))
    if not paths:
        paths = sorted(directory.rglob("*benchmarkData.json"))
    if not paths:
        raise FileNotFoundError(
            f"No native AndroidX *-benchmarkData.json files found under {directory}.",
        )
    for path in paths:
        payload = read_json(path)
        benchmarks = payload.get("benchmarks")
        if not isinstance(benchmarks, list):
            raise TypeError(f"{path} does not contain a benchmarks array.")
        for benchmark in benchmarks:
            if not isinstance(benchmark, dict):
                raise TypeError(f"{path} contains a non-object benchmark entry.")
            yield path, benchmark


def validate_resume_contract(directory: Path) -> Path:
    paths = sorted(directory.rglob(RESUME_CONTRACT_FILE))
    if len(paths) != 1:
        raise ValueError(
            f"Expected exactly one {RESUME_CONTRACT_FILE} under {directory}; "
            f"found {len(paths)}.",
        )
    path = paths[0]
    payload = read_json(path)
    if payload.get("status") != "assertions_passed_for_completed_iterations":
        raise ValueError(f"{path} does not report passed resume assertions.")
    if payload.get("expected_ui_tag") != EXPECTED_CACHED_UI_TAG:
        raise ValueError(f"{path} does not assert the expected cached-content tag.")
    if (
        payload.get("declared_raw_iterations") != 6
        or payload.get("warmup_iteration_ordinal") != 1
    ):
        raise ValueError(f"{path} does not describe the six-iteration protocol.")
    observations = payload.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ValueError(f"{path} must retain resume-contract observations.")
    if payload.get("completed_assertion_observations") != len(observations):
        raise ValueError(f"{path} has an inconsistent assertion-observation count.")
    observed_ordinals: list[int] = []
    for observation in observations:
        if not isinstance(observation, dict):
            raise TypeError(f"{path} contains a non-object contract observation.")
        observed_ordinals.append(
            int(observation.get("assertion_observation_ordinal", 0)),
        )
        pid = str(observation.get("pid", ""))
        activity_record_id = str(observation.get("activity_record_id", ""))
        if (
            not pid.isdigit()
            or not activity_record_id
            or observation.get("same_pid") is not True
            or observation.get("same_activity") is not True
        ):
            raise ValueError(f"{path} contains a failed PID/Activity assertion.")
    if tuple(observed_ordinals) != tuple(range(1, len(observations) + 1)):
        raise ValueError(f"{path} contains invalid raw-iteration ordinals.")
    return path


def extract_startup(args: argparse.Namespace) -> None:
    benchmark_data = Path(args.benchmark_data).resolve()
    output = Path(args.output).resolve()
    resume_contract = validate_resume_contract(benchmark_data)
    candidates: dict[str, list[tuple[Path, str, list[float]]]] = {
        scenario: [] for scenario in STARTUP_SCENARIOS
    }
    for source, benchmark in iter_benchmarks(benchmark_data):
        scenario = classify_startup_scenario(benchmark)
        if scenario is None:
            continue
        requested_metric = (
            args.cold_metric if scenario == "cached_cold" else args.resume_metric
        )
        metric_name, runs = select_metric(
            benchmark,
            scenario=scenario,
            requested_name=requested_metric,
        )
        candidates[scenario].append((source, metric_name, runs))

    selected: dict[str, tuple[Path, str, list[float]]] = {}
    for scenario, matches in candidates.items():
        unique: dict[tuple[str, tuple[float, ...]], tuple[Path, str, list[float]]] = {}
        for source, metric_name, runs in matches:
            unique[(metric_name, tuple(runs))] = (source, metric_name, runs)
        if len(unique) != 1:
            descriptions = [
                f"{source}:{metric_name}[{len(runs)}]"
                for source, metric_name, runs in matches
            ]
            raise ValueError(
                f"Expected one unique native benchmark for {scenario}; "
                f"observed {descriptions or 'none'}.",
            )
        selected[scenario] = next(iter(unique.values()))

    rows: list[dict[str, object]] = []
    benchmark_success = args.benchmark_exit_status == 0
    for scenario in STARTUP_SCENARIOS:
        source, metric_name, runs = selected[scenario]
        if len(runs) != 6:
            raise ValueError(
                f"{source}:{metric_name} has {len(runs)} runs; expected exactly six.",
            )
        for retained_iteration, raw_iteration in enumerate(range(2, 7), start=1):
            rows.append(
                {
                    "track": "startup",
                    "scenario": scenario,
                    "session_id": args.session_id,
                    "iteration": retained_iteration,
                    "raw_iteration": raw_iteration,
                    "metric": metric_name,
                    "duration_ms": rounded(runs[raw_iteration - 1]),
                    "success": str(benchmark_success).lower(),
                    "outcome": (
                        "macrobenchmark_assertions_passed"
                        if benchmark_success
                        else "benchmark_process_failed"
                    ),
                    "source_file": source.relative_to(benchmark_data).as_posix(),
                },
            )
    write_csv(output, rows)
    print(
        f"Extracted 10 retained startup measurements for {args.session_id}; "
        "raw iteration 1 remains only in native benchmarkData JSON. "
        f"Validated resume assertions in {resume_contract.name}.",
    )


def require_columns(
    rows: list[dict[str, str]],
    columns: set[str],
    *,
    source: Path,
) -> None:
    if not rows:
        raise ValueError(f"{source} contains no data rows.")
    missing = columns.difference(rows[0])
    if missing:
        raise ValueError(f"{source} is missing columns: {sorted(missing)}")


def validate_startup_rows(
    rows: list[dict[str, str]],
    *,
    source: Path,
    session_id: str,
    require_success: bool,
) -> dict[str, list[float]]:
    require_columns(
        rows,
        {
            "track",
            "scenario",
            "session_id",
            "iteration",
            "raw_iteration",
            "metric",
            "duration_ms",
            "success",
            "outcome",
        },
        source=source,
    )
    grouped: dict[str, list[dict[str, str]]] = {
        scenario: [] for scenario in STARTUP_SCENARIOS
    }
    for row in rows:
        scenario = row["scenario"]
        if scenario not in grouped:
            raise ValueError(f"{source} contains an unexpected scenario: {scenario}")
        if row["track"] != "startup" or row["session_id"] != session_id:
            raise ValueError(f"{source} contains a mismatched track/session row.")
        if require_success and not as_bool(row["success"], source=source):
            raise ValueError(f"{source} contains a failed retained startup sample.")
        grouped[scenario].append(row)

    durations: dict[str, list[float]] = {}
    for scenario, group in grouped.items():
        ordered = sorted(group, key=lambda row: int(row["iteration"]))
        iterations = tuple(int(row["iteration"]) for row in ordered)
        raw_iterations = tuple(int(row["raw_iteration"]) for row in ordered)
        if iterations != EXPECTED_RETAINED_ITERATIONS:
            raise ValueError(
                f"{source} {scenario} retained iterations are {iterations}, "
                f"expected {EXPECTED_RETAINED_ITERATIONS}.",
            )
        if raw_iterations != EXPECTED_RAW_ITERATIONS:
            raise ValueError(
                f"{source} {scenario} raw iterations are {raw_iterations}, "
                f"expected {EXPECTED_RAW_ITERATIONS}.",
            )
        metric_names = {row["metric"] for row in ordered}
        expected_metric = EXPECTED_STARTUP_METRICS[scenario]
        if metric_names != {expected_metric}:
            raise ValueError(
                f"{source} {scenario} uses {metric_names}; "
                f"expected only {expected_metric!r}.",
            )
        durations[scenario] = [
            positive_float(row["duration_ms"], source=source) for row in ordered
        ]
    return durations


def validate_graph_rows(
    rows: list[dict[str, str]],
    *,
    source: Path,
    session_id: str,
    node_order: Sequence[int],
    require_success: bool,
) -> dict[tuple[str, int], list[float]]:
    require_columns(
        rows,
        {
            "track",
            "scenario",
            "session_id",
            "node_order_index",
            "pair_index",
            "node_count",
            "edge_count",
            "phase",
            "render_id",
            "webview_instance_id",
            "duration_ms",
            "dom_node_count",
            "dom_edge_count",
            "tick_count",
            "success",
            "outcome",
        },
        source=source,
    )
    if len(rows) != 40:
        raise ValueError(f"{source} has {len(rows)} rows; expected exactly 40.")

    grouped: dict[tuple[str, int], list[dict[str, str]]] = {}
    render_ids: set[str] = set()
    new_instance_ids: set[str] = set()
    pair_instances: dict[tuple[int, int], dict[str, str]] = {}
    for row in rows:
        if (
            row["track"] != "graph"
            or row["scenario"] != "visual_state_ready"
            or row["session_id"] != session_id
        ):
            raise ValueError(f"{source} contains a mismatched graph identity row.")
        phase = row["phase"]
        if phase not in GRAPH_PHASES:
            raise ValueError(f"{source} contains an unexpected graph phase: {phase}")
        node_count = positive_int(row["node_count"], source=source)
        if node_count not in EDGE_COUNTS:
            raise ValueError(
                f"{source} contains an unexpected node count: {node_count}"
            )
        order_index = positive_int(row["node_order_index"], source=source)
        if order_index > len(node_order) or node_order[order_index - 1] != node_count:
            raise ValueError(f"{source} violates the declared node order.")
        pair_index = positive_int(row["pair_index"], source=source)
        if pair_index not in EXPECTED_RETAINED_ITERATIONS:
            raise ValueError(f"{source} contains an invalid pair index: {pair_index}")
        expected_edges = EDGE_COUNTS[node_count]
        edge_count = positive_int(row["edge_count"], source=source, allow_zero=True)
        dom_nodes = positive_int(row["dom_node_count"], source=source)
        dom_edges = positive_int(
            row["dom_edge_count"],
            source=source,
            allow_zero=True,
        )
        tick_count = positive_int(row["tick_count"], source=source)
        if edge_count != expected_edges or dom_edges != expected_edges:
            raise ValueError(f"{source} contains an edge-count mismatch.")
        if dom_nodes != node_count or tick_count < 1:
            raise ValueError(f"{source} contains an invalid visual-state result.")
        if require_success and (
            not as_bool(row["success"], source=source)
            or row["outcome"] != "visual_state_ready"
        ):
            raise ValueError(f"{source} contains a failed graph sample.")
        render_id = row["render_id"].strip()
        instance_id = row["webview_instance_id"].strip()
        if not render_id or render_id in render_ids or not instance_id:
            raise ValueError(f"{source} contains missing or duplicate renderer IDs.")
        render_ids.add(render_id)
        pair_key = (node_count, pair_index)
        pair_instances.setdefault(pair_key, {})[phase] = instance_id
        if phase == "new_webview_instance":
            if instance_id in new_instance_ids:
                raise ValueError(
                    f"{source} reused a new-WebView instance across pairs."
                )
            new_instance_ids.add(instance_id)
        grouped.setdefault((phase, node_count), []).append(row)

    expected_groups = {
        (phase, node_count) for phase in GRAPH_PHASES for node_count in EDGE_COUNTS
    }
    if set(grouped) != expected_groups:
        raise ValueError(f"{source} has incomplete graph phase/node groups.")
    for key, group in grouped.items():
        pair_indices = sorted(int(row["pair_index"]) for row in group)
        if tuple(pair_indices) != EXPECTED_RETAINED_ITERATIONS:
            raise ValueError(f"{source} group {key} has invalid pair indices.")
    for pair_key, instances in pair_instances.items():
        if set(instances) != set(GRAPH_PHASES):
            raise ValueError(f"{source} pair {pair_key} is incomplete.")
        if instances["new_webview_instance"] != instances["reused_webview"]:
            raise ValueError(f"{source} pair {pair_key} did not reuse its WebView.")

    return {
        key: [
            positive_float(row["duration_ms"], source=source)
            for row in sorted(group, key=lambda row: int(row["pair_index"]))
        ]
        for key, group in grouped.items()
    }


def validate_artifact_hashes(run_root: Path, completion: dict[str, Any]) -> None:
    expected = completion.get("artifact_sha256")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("completed.json must contain a non-empty artifact_sha256 map.")
    for relative_path, expected_hash in expected.items():
        artifact = run_root / str(relative_path)
        if not artifact.is_file():
            raise FileNotFoundError(f"Missing retained session artifact: {artifact}")
        actual_hash = sha256(artifact)
        if actual_hash != expected_hash:
            raise ValueError(
                f"Artifact hash mismatch for {artifact}: "
                f"{actual_hash} != {expected_hash}",
            )


def validate_experiment_provenance(
    run_root: Path,
    experiment_manifest: dict[str, Any],
) -> dict[str, str]:
    required_identity = ("run_id", "source_revision", "source_branch")
    for field in required_identity:
        if (
            not isinstance(experiment_manifest.get(field), str)
            or not experiment_manifest[field]
        ):
            raise ValueError(f"Experiment manifest has an invalid {field}.")

    environment = experiment_manifest.get("environment")
    if (
        not isinstance(environment, dict)
        or environment.get("backend_used") is not False
        or environment.get("live_credentials_required") is not False
    ):
        raise ValueError("The resource experiment must use only controlled local data.")

    provenance = experiment_manifest.get("provenance")
    expected_hash_fields = (
        "runner_sha256",
        "analyzer_sha256",
        "startup_app_apk_sha256",
        "startup_benchmark_apk_sha256",
        "graph_app_apk_sha256",
        "graph_test_apk_sha256",
    )
    if not isinstance(provenance, dict) or set(provenance) != set(expected_hash_fields):
        raise ValueError(
            "Experiment provenance does not contain the exact required hashes."
        )
    for field in expected_hash_fields:
        digest = provenance[field]
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"Experiment provenance {field} is not a SHA-256 digest.")
        try:
            int(digest, 16)
        except ValueError as error:
            raise ValueError(
                f"Experiment provenance {field} is not a SHA-256 digest.",
            ) from error

    build_artifacts_path = run_root / "build_artifacts.json"
    if not build_artifacts_path.is_file():
        raise FileNotFoundError(
            f"Missing frozen build-artifact inventory: {build_artifacts_path}",
        )
    build_artifacts = read_json(build_artifacts_path)
    if (
        build_artifacts.get("live_credentials_embedded") is not False
        or build_artifacts.get("apks_retained") is not False
    ):
        raise ValueError("Build-artifact credential or retention boundary is invalid.")
    build_to_provenance = {
        "startup_app": "startup_app_apk_sha256",
        "startup_benchmark": "startup_benchmark_apk_sha256",
        "graph_app": "graph_app_apk_sha256",
        "graph_test": "graph_test_apk_sha256",
    }
    for build_key, provenance_key in build_to_provenance.items():
        build_entry = build_artifacts.get(build_key)
        if (
            not isinstance(build_entry, dict)
            or build_entry.get("sha256") != provenance[provenance_key]
        ):
            raise ValueError(
                f"Frozen build artifact {build_key} does not match experiment provenance.",
            )
    return {field: str(provenance[field]) for field in expected_hash_fields}


def validate_one_session(
    run_root: Path,
    session_dir: Path,
    *,
    require_success: bool,
    experiment_manifest: dict[str, Any] | None = None,
    experiment_provenance: dict[str, str] | None = None,
) -> SessionSummary:
    manifest_path = session_dir / "session_manifest.json"
    completed_path = session_dir / "completed.json"
    startup_path = session_dir / "startup_measurements.csv"
    graph_path = session_dir / "graph_measurements.csv"
    for path in (manifest_path, completed_path, startup_path, graph_path):
        if not path.is_file():
            raise FileNotFoundError(f"Missing formal session artifact: {path}")
    manifest = read_json(manifest_path)
    completion = read_json(completed_path)
    if completion.get("status") != "completed":
        raise ValueError(f"{completed_path} does not mark a completed session.")
    validate_artifact_hashes(run_root, completion)
    if experiment_manifest is not None:
        for field in ("run_id", "source_revision", "source_branch"):
            if manifest.get(field) != experiment_manifest.get(field):
                raise ValueError(
                    f"{manifest_path} {field} does not match the experiment manifest.",
                )
        if manifest.get("backend_used") is not False:
            raise ValueError(f"{manifest_path} must record backend_used=false.")
    if (
        experiment_provenance is not None
        and manifest.get("provenance") != experiment_provenance
    ):
        raise ValueError(
            f"{manifest_path} provenance does not match the frozen experiment build.",
        )

    session_id = str(manifest["session_id"])
    block = int(manifest["block"])
    position = int(manifest["sequence_position"])
    config_id = str(manifest["config_id"])
    if block not in BLOCK_ORDERS or config_id not in CONFIGS:
        raise ValueError(f"{manifest_path} contains an invalid block/config.")
    if position not in range(1, len(BLOCK_ORDERS[block]) + 1):
        raise ValueError(f"{manifest_path} contains an invalid sequence position.")
    if BLOCK_ORDERS[block][position - 1] != config_id:
        raise ValueError(f"{manifest_path} violates the complementary block order.")
    node_order = tuple(int(value) for value in manifest["graph_node_order"])
    if node_order != NODE_ORDERS[block]:
        raise ValueError(f"{manifest_path} contains the wrong node order.")
    cpu_cores, ram_mb = CONFIGS[config_id]
    if (
        int(manifest["requested_cpu_cores"]) != cpu_cores
        or int(manifest["requested_ram_mb"]) != ram_mb
        or int(manifest["runtime_cpu_cores"]) != cpu_cores
    ):
        raise ValueError(f"{manifest_path} contains a resource mismatch.")
    runtime_memory_kb = int(manifest["runtime_memory_kb"])
    memory_bounds_kb = (
        (1_500_000, 2_400_000) if ram_mb == 2048 else (5_000_000, 6_600_000)
    )
    if not memory_bounds_kb[0] <= runtime_memory_kb <= memory_bounds_kb[1]:
        raise ValueError(
            f"{manifest_path} contains an out-of-cell runtime memory value."
        )

    startup = validate_startup_rows(
        read_csv(startup_path),
        source=startup_path,
        session_id=session_id,
        require_success=require_success,
    )
    graph = validate_graph_rows(
        read_csv(graph_path),
        source=graph_path,
        session_id=session_id,
        node_order=node_order,
        require_success=require_success,
    )
    graph_medians = {
        (phase, nodes): rounded(statistics.median(values))
        for (phase, nodes), values in graph.items()
    }
    return SessionSummary(
        session_id=session_id,
        block=block,
        sequence_position=position,
        config_id=config_id,
        cpu_cores=cpu_cores,
        ram_mb=ram_mb,
        boot_id=str(manifest["boot_id"]),
        cached_cold_ms=rounded(statistics.median(startup["cached_cold"])),
        foreground_resume_ms=rounded(
            statistics.median(startup["foreground_resume"]),
        ),
        graph_new_1_ms=graph_medians[("new_webview_instance", 1)],
        graph_new_12_ms=graph_medians[("new_webview_instance", 12)],
        graph_new_25_ms=graph_medians[("new_webview_instance", 25)],
        graph_new_50_ms=graph_medians[("new_webview_instance", 50)],
        graph_reused_1_ms=graph_medians[("reused_webview", 1)],
        graph_reused_12_ms=graph_medians[("reused_webview", 12)],
        graph_reused_25_ms=graph_medians[("reused_webview", 25)],
        graph_reused_50_ms=graph_medians[("reused_webview", 50)],
    )


def metric_map(summary: SessionSummary) -> dict[str, float]:
    return {
        "cached_cold_ms": summary.cached_cold_ms,
        "foreground_resume_ms": summary.foreground_resume_ms,
        "graph_new_1_ms": summary.graph_new_1_ms,
        "graph_new_12_ms": summary.graph_new_12_ms,
        "graph_new_25_ms": summary.graph_new_25_ms,
        "graph_new_50_ms": summary.graph_new_50_ms,
        "graph_reused_1_ms": summary.graph_reused_1_ms,
        "graph_reused_12_ms": summary.graph_reused_12_ms,
        "graph_reused_25_ms": summary.graph_reused_25_ms,
        "graph_reused_50_ms": summary.graph_reused_50_ms,
    }


def configuration_rows(summaries: Sequence[SessionSummary]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for config_id, (cpu_cores, ram_mb) in CONFIGS.items():
        sessions = sorted(
            (summary for summary in summaries if summary.config_id == config_id),
            key=lambda summary: summary.block,
        )
        if len(sessions) != 2:
            raise ValueError(f"{config_id} has {len(sessions)} sessions; expected two.")
        for metric in metric_map(sessions[0]):
            first = metric_map(sessions[0])[metric]
            second = metric_map(sessions[1])[metric]
            rows.append(
                {
                    "metric": metric,
                    "config_id": config_id,
                    "cpu_cores": cpu_cores,
                    "ram_mb": ram_mb,
                    "block_1_session_median_ms": first,
                    "block_2_session_median_ms": second,
                    "median_of_two_ms": rounded(statistics.median((first, second))),
                    "observed_min_ms": rounded(min(first, second)),
                    "observed_max_ms": rounded(max(first, second)),
                    "observed_range_ms": rounded(abs(second - first)),
                },
            )
    return rows


def effect_rows(summaries: Sequence[SessionSummary]) -> list[dict[str, object]]:
    by_cell = {(summary.block, summary.config_id): summary for summary in summaries}
    rows: list[dict[str, object]] = []
    for block in BLOCK_ORDERS:
        values_by_config = {
            config_id: metric_map(by_cell[(block, config_id)]) for config_id in CONFIGS
        }
        for metric in metric_map(next(iter(by_cell.values()))):
            values = {
                config_id: metrics[metric]
                for config_id, metrics in values_by_config.items()
            }

            def change(high: float, low: float) -> float:
                return rounded((high / low - 1.0) * 100.0)

            interaction_ratio = (
                values["cpu4_ram6gb"]
                / values["cpu4_ram2gb"]
                / (values["cpu2_ram6gb"] / values["cpu2_ram2gb"])
            )
            rows.append(
                {
                    "metric": metric,
                    "block": block,
                    "cpu_at_2g_percent": change(
                        values["cpu4_ram2gb"],
                        values["cpu2_ram2gb"],
                    ),
                    "cpu_at_6g_percent": change(
                        values["cpu4_ram6gb"],
                        values["cpu2_ram6gb"],
                    ),
                    "ram_at_2cpu_percent": change(
                        values["cpu2_ram6gb"],
                        values["cpu2_ram2gb"],
                    ),
                    "ram_at_4cpu_percent": change(
                        values["cpu4_ram6gb"],
                        values["cpu4_ram2gb"],
                    ),
                    "cpu_x_ram_interaction_percent": rounded(
                        (interaction_ratio - 1.0) * 100.0,
                    ),
                },
            )
    return rows


def graph_rows(summaries: Sequence[SessionSummary]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for config_id, (cpu_cores, ram_mb) in CONFIGS.items():
        sessions = sorted(
            (summary for summary in summaries if summary.config_id == config_id),
            key=lambda summary: summary.block,
        )
        for phase, prefix in (
            ("new_webview_instance", "graph_new"),
            ("reused_webview", "graph_reused"),
        ):
            for nodes in EDGE_COUNTS:
                metric = f"{prefix}_{nodes}_ms"
                first = metric_map(sessions[0])[metric]
                second = metric_map(sessions[1])[metric]
                rows.append(
                    {
                        "config_id": config_id,
                        "cpu_cores": cpu_cores,
                        "ram_mb": ram_mb,
                        "phase": phase,
                        "node_count": nodes,
                        "block_1_session_median_ms": first,
                        "block_2_session_median_ms": second,
                        "median_of_two_ms": rounded(
                            statistics.median((first, second)),
                        ),
                        "observed_min_ms": rounded(min(first, second)),
                        "observed_max_ms": rounded(max(first, second)),
                        "observed_range_ms": rounded(abs(second - first)),
                    },
                )
    return rows


def configure_plots() -> None:
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.edgecolor": "#A8B4BA",
            "axes.labelcolor": "#20303C",
            "axes.titlecolor": "#20303C",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": "#20303C",
            "ytick.color": "#20303C",
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "grid.color": "#DDE5E7",
            "grid.linewidth": 0.7,
        },
    )


def save_figure(figure: Any, output_dir: Path, name: str) -> None:
    import matplotlib.pyplot as plt

    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        figure.savefig(
            figure_dir / f"{name}.{suffix}",
            dpi=220,
            bbox_inches="tight",
        )
    plt.close(figure)


def plot_graph_scaling(
    rows: Sequence[dict[str, object]],
    output_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(1, 2, figsize=(10.2, 4.4), sharey=False)
    colors = {
        "cpu2_ram2gb": "#2E5EAA",
        "cpu2_ram6gb": "#D49A2A",
        "cpu4_ram2gb": "#146C73",
        "cpu4_ram6gb": "#8E5BA6",
    }
    for axis, phase, title in zip(
        axes,
        GRAPH_PHASES,
        ("New WebView instance", "Reused WebView"),
        strict=True,
    ):
        for config_id in CONFIGS:
            group = sorted(
                (
                    row
                    for row in rows
                    if row["config_id"] == config_id and row["phase"] == phase
                ),
                key=lambda row: int(row["node_count"]),
            )
            x_values = [int(row["node_count"]) for row in group]
            medians = [float(row["median_of_two_ms"]) for row in group]
            axis.plot(
                x_values,
                medians,
                marker="o",
                linewidth=1.8,
                color=colors[config_id],
                label=CONFIG_LABELS[config_id],
            )
            for block_key, marker in (
                ("block_1_session_median_ms", "x"),
                ("block_2_session_median_ms", "+"),
            ):
                axis.scatter(
                    x_values,
                    [float(row[block_key]) for row in group],
                    marker=marker,
                    s=34,
                    color=colors[config_id],
                    alpha=0.65,
                )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Graph nodes")
        axis.set_ylabel("Session median latency (ms)")
        axis.set_xticks(list(EDGE_COUNTS))
        axis.grid(axis="y")
    handles, labels = axes[0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        frameon=False,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, 1.08),
    )
    figure.tight_layout()
    save_figure(figure, output_dir, "graph_scaling")


def plot_resource_interactions(
    summaries: Sequence[SessionSummary],
    output_dir: Path,
) -> None:
    import matplotlib.pyplot as plt

    metrics = (
        ("cached_cold_ms", "Cached cold start"),
        ("foreground_resume_ms", "Foreground resume"),
        ("graph_new_50_ms", "50-node new WebView"),
        ("graph_reused_50_ms", "50-node reused WebView"),
    )
    figure, axes = plt.subplots(2, 2, figsize=(9.8, 7.4))
    for axis, (metric, title) in zip(axes.flat, metrics, strict=True):
        for cpu_cores, color in ((2, "#2E5EAA"), (4, "#146C73")):
            cell_medians: list[float] = []
            for ram_mb in (2048, 6144):
                cell_values = [
                    metric_map(summary)[metric]
                    for summary in summaries
                    if summary.cpu_cores == cpu_cores and summary.ram_mb == ram_mb
                ]
                cell_medians.append(statistics.median(cell_values))
                axis.scatter(
                    [ram_mb // 1024] * len(cell_values),
                    cell_values,
                    color=color,
                    alpha=0.55,
                    marker="x",
                    s=35,
                )
            axis.plot(
                [2, 6],
                cell_medians,
                color=color,
                marker="o",
                linewidth=1.8,
                label=f"{cpu_cores} CPU cores",
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Emulated RAM (GiB)")
        axis.set_ylabel("Session median latency (ms)")
        axis.set_xticks([2, 6])
        axis.grid(axis="y")
        axis.legend(frameon=False)
    figure.tight_layout()
    save_figure(figure, output_dir, "resource_interactions")


def analyze(args: argparse.Namespace) -> None:
    run_root = Path(args.run_root).resolve()
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir else run_root / "derived"
    )
    experiment_manifest_path = run_root / "experiment_manifest.json"
    if not experiment_manifest_path.is_file():
        raise FileNotFoundError(
            f"Missing formal experiment manifest: {experiment_manifest_path}",
        )
    experiment_manifest = read_json(experiment_manifest_path)
    if experiment_manifest.get("schema_version") != "android-formal-experiment-v2":
        raise ValueError("The run does not use android-formal-experiment-v2.")
    experiment_provenance = validate_experiment_provenance(
        run_root,
        experiment_manifest,
    )
    session_manifests = sorted(
        (run_root / "sessions").glob("*/session_manifest.json"),
    )
    if len(session_manifests) != 8:
        raise ValueError(
            f"{run_root} contains {len(session_manifests)} session manifests; "
            "expected exactly eight.",
        )
    summaries = [
        validate_one_session(
            run_root,
            manifest.parent,
            require_success=True,
            experiment_manifest=experiment_manifest,
            experiment_provenance=experiment_provenance,
        )
        for manifest in session_manifests
    ]
    summaries.sort(key=lambda summary: (summary.block, summary.sequence_position))
    observed_order = {
        block: tuple(
            summary.config_id for summary in summaries if summary.block == block
        )
        for block in BLOCK_ORDERS
    }
    if observed_order != BLOCK_ORDERS:
        raise ValueError(
            f"Observed session order {observed_order} != protocol {BLOCK_ORDERS}.",
        )
    boot_ids = [summary.boot_id for summary in summaries]
    if any(not boot_id for boot_id in boot_ids) or len(set(boot_ids)) != 8:
        raise ValueError("Every formal session must retain a unique non-empty boot ID.")

    session_rows = [asdict(summary) for summary in summaries]
    config_rows = configuration_rows(summaries)
    effects = effect_rows(summaries)
    graphs = graph_rows(summaries)
    write_csv(output_dir / "session_medians.csv", session_rows)
    write_csv(output_dir / "configuration_summary.csv", config_rows)
    write_csv(output_dir / "simple_effects_and_interactions.csv", effects)
    write_csv(output_dir / "graph_scaling.csv", graphs)

    summary_payload = {
        "schema_version": "android-formal-summary-v2",
        "run_id": experiment_manifest.get("run_id"),
        "source_revision": experiment_manifest.get("source_revision"),
        "method": {
            "analysis_unit": (
                "one separately cold-booted, wiped-data emulator session"
            ),
            "blocks": 2,
            "sessions": 8,
            "sessions_per_resource_cell": 2,
            "retained_startup_iterations_per_scenario_per_session": 5,
            "retained_graph_pairs_per_node_count_per_session": 5,
            "within_session_summary": "median",
            "across_session_summary": (
                "both raw session medians, median of two, and observed range"
            ),
            "p95_reported": False,
            "confidence_intervals_reported": False,
            "significance_tests_reported": False,
            "population_generalization": False,
        },
        "session_results": session_rows,
        "configuration_results": config_rows,
        "simple_effects_and_interactions": effects,
        "graph_scaling_results": graphs,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    configure_plots()
    plot_graph_scaling(graphs, output_dir)
    plot_resource_interactions(summaries, output_dir)
    print(
        f"Validated and summarized {len(summaries)} formal sessions under "
        f"{run_root}. No inferential statistics were calculated.",
    )


def validate_session(args: argparse.Namespace) -> None:
    startup_path = Path(args.startup_csv).resolve()
    graph_path = Path(args.graph_csv).resolve()
    node_order = tuple(int(value) for value in args.node_order.split(","))
    validate_startup_rows(
        read_csv(startup_path),
        source=startup_path,
        session_id=args.session_id,
        require_success=args.require_success,
    )
    validate_graph_rows(
        read_csv(graph_path),
        source=graph_path,
        session_id=args.session_id,
        node_order=node_order,
        require_success=args.require_success,
    )
    print(
        f"Validated 10 startup rows and 40 graph rows for {args.session_id}.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Formal Android CPU x RAM resource-matrix tooling.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser(
        "extract-startup",
        help="Extract retained runs from native AndroidX benchmarkData JSON.",
    )
    extract_parser.add_argument("--benchmark-data", required=True)
    extract_parser.add_argument("--session-id", required=True)
    extract_parser.add_argument("--output", required=True)
    extract_parser.add_argument("--benchmark-exit-status", required=True, type=int)
    extract_parser.add_argument("--cold-metric")
    extract_parser.add_argument("--resume-metric")
    extract_parser.set_defaults(handler=extract_startup)

    validate_parser = subparsers.add_parser(
        "validate-session",
        help="Validate one session's exact 10-row and 40-row contracts.",
    )
    validate_parser.add_argument("--startup-csv", required=True)
    validate_parser.add_argument("--graph-csv", required=True)
    validate_parser.add_argument("--session-id", required=True)
    validate_parser.add_argument("--node-order", required=True)
    validate_parser.add_argument(
        "--require-success",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    validate_parser.set_defaults(handler=validate_session)

    analyze_parser = subparsers.add_parser(
        "analyze",
        help="Validate all eight sessions and generate descriptive outputs.",
    )
    analyze_parser.add_argument("--run-root", required=True)
    analyze_parser.add_argument("--output-dir")
    analyze_parser.set_defaults(handler=analyze)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.handler(args)


if __name__ == "__main__":
    main()
