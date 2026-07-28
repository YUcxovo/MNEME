#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "matplotlib==3.10.3",
# ]
# ///
"""Validate and analyze the controlled Android CPU x RAM experiment."""

from __future__ import annotations

import csv
import itertools
import json
import math
import re
import statistics
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation" / "android-factorial"
RAW_ROOT = EVALUATION_DIR / "raw"
FIGURE_DIR = EVALUATION_DIR / "figures"

CONFIGS = {
    "cpu2_ram2gb": (2, 2048),
    "cpu2_ram6gb": (2, 6144),
    "cpu4_ram2gb": (4, 2048),
    "cpu4_ram6gb": (4, 6144),
}
CONFIG_ORDER = list(CONFIGS)
CONFIG_LABELS = {
    "cpu2_ram2gb": "2 cores / 2 GiB",
    "cpu2_ram6gb": "2 cores / 6 GiB",
    "cpu4_ram2gb": "4 cores / 2 GiB",
    "cpu4_ram6gb": "4 cores / 6 GiB",
}
NODE_COUNTS = (1, 12, 25, 50)

REQUIRED_FILES = (
    "app_start_measurements.csv",
    "state_measurements.csv",
    "graph_measurements.csv",
    "graph_state_measurements.csv",
    "event_sync_measurements.csv",
    "environment.json",
    "run_manifest.json",
    "instrumentation_measurement.txt",
    "completed.json",
)


@dataclass(frozen=True)
class RunSummary:
    config_id: str
    block: int
    sequence_position: int
    cpu_cores: int
    ram_mb: int
    controlled_samples: int
    successful_samples: int
    success_rate: float
    functional_tests: int
    measurement_tests: int
    cold_start_p50_ms: float
    cold_start_p95_ms: float
    warm_resume_p50_ms: float
    warm_resume_p95_ms: float
    polling_p50_ms: float
    event_retry_p50_ms: float
    graph_50_cold_p50_ms: float
    graph_50_cold_p95_ms: float
    graph_50_warm_p50_ms: float
    graph_50_warm_p95_ms: float
    graph_50_select_p50_ms: float
    graph_50_select_p95_ms: float
    graph_50_reuse_ratio: float


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def as_success(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Unexpected success value: {value!r}")
    return normalized == "true"


def nearest_rank(values: Iterable[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("A percentile requires at least one value.")
    return ordered[max(0, math.ceil(percentile * len(ordered)) - 1)]


def percentile_pair(values: Iterable[float]) -> tuple[float, float]:
    collected = list(values)
    return (
        round(statistics.median(collected), 3),
        round(nearest_rank(collected, 0.95), 3),
    )


def quartiles(values: Iterable[float]) -> tuple[float, float]:
    collected = list(values)
    q1, _, q3 = statistics.quantiles(collected, n=4, method="inclusive")
    return round(q1, 3), round(q3, 3)


def exact_bootstrap_median_ci(values: Iterable[float]) -> tuple[float, float]:
    collected = list(values)
    distribution = [
        statistics.median(collected[index] for index in indices)
        for indices in itertools.product(range(len(collected)), repeat=len(collected))
    ]
    return (
        round(nearest_rank(distribution, 0.025), 3),
        round(nearest_rank(distribution, 0.975), 3),
    )


def require_group_count(
    rows: list[dict[str, str]],
    keys: tuple[str, ...],
    expected: dict[tuple[str, ...], int],
    source: Path,
) -> None:
    observed: dict[tuple[str, ...], int] = {}
    for row in rows:
        key = tuple(row[item] for item in keys)
        observed[key] = observed.get(key, 0) + 1
    if observed != expected:
        raise ValueError(
            f"{source} has unexpected sample groups.\nExpected: {expected}\nObserved: {observed}",
        )


def instrumentation_count(path: Path, expected: int) -> int:
    match = re.search(r"^OK \((\d+) tests?\)$", path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"{path} does not contain a passing instrumentation result.")
    count = int(match.group(1))
    if count != expected:
        raise ValueError(f"{path} passed {count} tests; expected {expected}.")
    return count


def scenario_values(
    rows: list[dict[str, str]],
    *,
    scenario: str,
    duration_key: str = "duration_ms",
) -> list[float]:
    return [float(row[duration_key]) for row in rows if row["scenario"] == scenario]


def graph_values(
    rows: list[dict[str, str]],
    *,
    scenario: str,
    phase: str,
    node_count: int,
) -> list[float]:
    return [
        float(row["duration_ms"])
        for row in rows
        if row["scenario"] == scenario
        and row["phase"] == phase
        and row["node_count"] == str(node_count)
    ]


def validate_run(config_id: str, block: int) -> tuple[RunSummary, dict[str, object]]:
    run_dir = RAW_ROOT / config_id / f"run-{block:02d}"
    for file_name in REQUIRED_FILES:
        if not (run_dir / file_name).is_file():
            raise FileNotFoundError(f"Missing factorial artifact: {run_dir / file_name}")

    startup = read_csv(run_dir / "app_start_measurements.csv")
    state = read_csv(run_dir / "state_measurements.csv")
    graph = read_csv(run_dir / "graph_measurements.csv")
    graph_state = read_csv(run_dir / "graph_state_measurements.csv")
    event = read_csv(run_dir / "event_sync_measurements.csv")
    environment = read_json(run_dir / "environment.json")
    manifest = read_json(run_dir / "run_manifest.json")

    require_group_count(
        startup,
        ("scenario",),
        {("cold_process",): 20, ("warm_task_resume",): 20},
        run_dir / "app_start_measurements.csv",
    )
    require_group_count(
        state,
        ("scenario",),
        {
            ("live_seed",): 30,
            ("cached_warm_start",): 30,
            ("cached_offline_disclosure",): 30,
            ("cached_server_failure_disclosure",): 30,
            ("invalid_cache_error",): 30,
            ("three_stage_job_polling",): 10,
        },
        run_dir / "state_measurements.csv",
    )
    graph_expected = {}
    for scenario in ("render_ready", "select_node"):
        for phase, count in (("cold_webview", 20), ("warm_update", 30)):
            for nodes in NODE_COUNTS:
                graph_expected[(scenario, phase, str(nodes))] = count
    require_group_count(
        graph,
        ("scenario", "phase", "node_count"),
        graph_expected,
        run_dir / "graph_measurements.csv",
    )
    require_group_count(
        graph_state,
        ("state",),
        {("ready",): 30, ("fallback",): 30, ("empty",): 30},
        run_dir / "graph_state_measurements.csv",
    )
    require_group_count(
        event,
        ("scenario",),
        {
            ("queue_write",): 30,
            ("retryable_http_failure",): 30,
            ("retry_success",): 30,
            ("duplicate_replay",): 30,
        },
        run_dir / "event_sync_measurements.csv",
    )

    all_rows = startup + state + graph + graph_state + event
    if len(all_rows) != 810:
        raise ValueError(f"{run_dir} contains {len(all_rows)} samples; expected 810.")
    successes = sum(as_success(row["success"]) for row in all_rows)
    measurement_tests = instrumentation_count(
        run_dir / "instrumentation_measurement.txt",
        4,
    )
    functional_tests = 0
    functional_path = run_dir / "instrumentation_functional.txt"
    if block == 1:
        if not functional_path.is_file():
            raise FileNotFoundError(f"Missing first-block functional result: {functional_path}")
        functional_tests = instrumentation_count(functional_path, 11)
    elif functional_path.exists():
        raise ValueError(f"Unexpected repeated functional suite: {functional_path}")

    expected_cpu, expected_ram = CONFIGS[config_id]
    if int(manifest["requested_cpu_cores"]) != expected_cpu:
        raise ValueError(f"{run_dir} has an unexpected requested CPU count.")
    if int(manifest["requested_ram_mb"]) != expected_ram:
        raise ValueError(f"{run_dir} has an unexpected requested RAM value.")
    if int(environment["android_sdk"]) != 34:
        raise ValueError(f"{run_dir} did not run Android API 34.")
    if int(environment["available_processors"]) != expected_cpu:
        raise ValueError(f"{run_dir} application runtime observed the wrong CPU count.")
    if str(manifest["screen_size"]) != "1080x2400":
        raise ValueError(f"{run_dir} has an unexpected screen size.")
    if int(manifest["screen_density_dpi"]) != 420:
        raise ValueError(f"{run_dir} has an unexpected screen density.")
    if int(manifest["runtime_page_size_bytes"]) != 4096:
        raise ValueError(f"{run_dir} has an unexpected page size.")

    cold = scenario_values(startup, scenario="cold_process", duration_key="wait_time_ms")
    warm = scenario_values(startup, scenario="warm_task_resume", duration_key="wait_time_ms")
    polling = scenario_values(state, scenario="three_stage_job_polling")
    event_retry = scenario_values(event, scenario="retry_success")
    graph_cold = graph_values(
        graph,
        scenario="render_ready",
        phase="cold_webview",
        node_count=50,
    )
    graph_warm = graph_values(
        graph,
        scenario="render_ready",
        phase="warm_update",
        node_count=50,
    )
    graph_select = graph_values(
        graph,
        scenario="select_node",
        phase="warm_update",
        node_count=50,
    )

    cold_p50, cold_p95 = percentile_pair(cold)
    warm_p50, warm_p95 = percentile_pair(warm)
    graph_cold_p50, graph_cold_p95 = percentile_pair(graph_cold)
    graph_warm_p50, graph_warm_p95 = percentile_pair(graph_warm)
    graph_select_p50, graph_select_p95 = percentile_pair(graph_select)

    summary = RunSummary(
        config_id=config_id,
        block=block,
        sequence_position=int(manifest["sequence_position"]),
        cpu_cores=expected_cpu,
        ram_mb=expected_ram,
        controlled_samples=len(all_rows),
        successful_samples=successes,
        success_rate=round(successes / len(all_rows), 6),
        functional_tests=functional_tests,
        measurement_tests=measurement_tests,
        cold_start_p50_ms=cold_p50,
        cold_start_p95_ms=cold_p95,
        warm_resume_p50_ms=warm_p50,
        warm_resume_p95_ms=warm_p95,
        polling_p50_ms=round(statistics.median(polling), 3),
        event_retry_p50_ms=round(statistics.median(event_retry), 3),
        graph_50_cold_p50_ms=graph_cold_p50,
        graph_50_cold_p95_ms=graph_cold_p95,
        graph_50_warm_p50_ms=graph_warm_p50,
        graph_50_warm_p95_ms=graph_warm_p95,
        graph_50_select_p50_ms=graph_select_p50,
        graph_50_select_p95_ms=graph_select_p95,
        graph_50_reuse_ratio=round(graph_cold_p50 / graph_warm_p50, 3),
    )
    return summary, {
        "environment": environment,
        "run_manifest": manifest,
        "graph_rows": graph,
    }


def write_rows(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        raise ValueError(f"Cannot write an empty table: {path}")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def configuration_summaries(runs: list[RunSummary]) -> list[dict[str, object]]:
    metric_keys = (
        "cold_start_p50_ms",
        "warm_resume_p50_ms",
        "graph_50_cold_p50_ms",
        "graph_50_warm_p50_ms",
        "graph_50_select_p50_ms",
        "graph_50_reuse_ratio",
    )
    rows = []
    for config_id in CONFIG_ORDER:
        group = [run for run in runs if run.config_id == config_id]
        cpu, ram = CONFIGS[config_id]
        row: dict[str, object] = {
            "config_id": config_id,
            "cpu_cores": cpu,
            "ram_mb": ram,
            "independent_runs": len(group),
            "controlled_samples": sum(run.controlled_samples for run in group),
            "successful_samples": sum(run.successful_samples for run in group),
            "functional_tests": sum(run.functional_tests for run in group),
            "measurement_tests": sum(run.measurement_tests for run in group),
        }
        for key in metric_keys:
            values = [float(getattr(run, key)) for run in group]
            q1, q3 = quartiles(values)
            ci_low, ci_high = exact_bootstrap_median_ci(values)
            row[f"{key}_median"] = round(statistics.median(values), 3)
            row[f"{key}_q1"] = q1
            row[f"{key}_q3"] = q3
            row[f"{key}_bootstrap95_low"] = ci_low
            row[f"{key}_bootstrap95_high"] = ci_high
        rows.append(row)
    return rows


def factor_effects(runs: list[RunSummary]) -> list[dict[str, object]]:
    metrics = {
        "cold_start_p50_ms": "Cold process start",
        "warm_resume_p50_ms": "Task foreground / resume",
        "graph_50_cold_p50_ms": "50-node new WebView",
        "graph_50_warm_p50_ms": "50-node existing WebView",
        "graph_50_select_p50_ms": "50-node selection callback",
    }
    by_block = {(run.block, run.config_id): run for run in runs}
    rows = []
    for metric, label in metrics.items():
        block_effects = {"CPU": [], "RAM": [], "CPUxRAM": []}
        for block in range(1, 5):
            values = {
                config_id: float(getattr(by_block[(block, config_id)], metric))
                for config_id in CONFIG_ORDER
            }
            cpu_low = statistics.mean(
                [values["cpu2_ram2gb"], values["cpu2_ram6gb"]],
            )
            cpu_high = statistics.mean(
                [values["cpu4_ram2gb"], values["cpu4_ram6gb"]],
            )
            ram_low = statistics.mean(
                [values["cpu2_ram2gb"], values["cpu4_ram2gb"]],
            )
            ram_high = statistics.mean(
                [values["cpu2_ram6gb"], values["cpu4_ram6gb"]],
            )
            interaction_ratio = (
                values["cpu4_ram6gb"]
                / values["cpu4_ram2gb"]
                / (values["cpu2_ram6gb"] / values["cpu2_ram2gb"])
            )
            block_effects["CPU"].append((cpu_high / cpu_low - 1.0) * 100.0)
            block_effects["RAM"].append((ram_high / ram_low - 1.0) * 100.0)
            block_effects["CPUxRAM"].append((interaction_ratio - 1.0) * 100.0)

        for factor, values in block_effects.items():
            q1, q3 = quartiles(values)
            ci_low, ci_high = exact_bootstrap_median_ci(values)
            rows.append(
                {
                    "metric": metric,
                    "metric_label": label,
                    "factor": factor,
                    "independent_blocks": len(values),
                    "median_percent_change": round(statistics.median(values), 3),
                    "q1_percent_change": q1,
                    "q3_percent_change": q3,
                    "bootstrap95_low": ci_low,
                    "bootstrap95_high": ci_high,
                    "direction": (
                        "lower_latency" if statistics.median(values) < 0 else "higher_latency"
                    ),
                },
            )
    return rows


def node_summaries(
    metadata: dict[tuple[str, int], dict[str, object]],
) -> list[dict[str, object]]:
    rows = []
    for config_id in CONFIG_ORDER:
        for phase in ("cold_webview", "warm_update"):
            for node_count in NODE_COUNTS:
                run_medians = []
                for block in range(1, 5):
                    graph_rows = metadata[(config_id, block)]["graph_rows"]
                    if not isinstance(graph_rows, list):
                        raise TypeError("graph_rows must be a list.")
                    values = graph_values(
                        graph_rows,
                        scenario="render_ready",
                        phase=phase,
                        node_count=node_count,
                    )
                    run_medians.append(statistics.median(values))
                q1, q3 = quartiles(run_medians)
                ci_low, ci_high = exact_bootstrap_median_ci(run_medians)
                rows.append(
                    {
                        "config_id": config_id,
                        "cpu_cores": CONFIGS[config_id][0],
                        "ram_mb": CONFIGS[config_id][1],
                        "phase": phase,
                        "node_count": node_count,
                        "independent_runs": len(run_medians),
                        "median_of_run_medians_ms": round(
                            statistics.median(run_medians),
                            3,
                        ),
                        "q1_ms": q1,
                        "q3_ms": q3,
                        "bootstrap95_low_ms": ci_low,
                        "bootstrap95_high_ms": ci_high,
                    },
                )
    return rows


def configure_plots() -> None:
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


def save_figure(figure: plt.Figure, name: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("png", "pdf"):
        figure.savefig(
            FIGURE_DIR / f"{name}.{suffix}",
            dpi=220,
            bbox_inches="tight",
        )
    plt.close(figure)


def plot_webview_reuse(runs: list[RunSummary]) -> None:
    figure, axes = plt.subplots(2, 2, figsize=(9.4, 7.2), sharey=True)
    colors = ["#2E5EAA", "#146C73", "#D49A2A", "#8E5BA6"]
    for axis, config_id in zip(axes.flat, CONFIG_ORDER, strict=True):
        group = sorted(
            (run for run in runs if run.config_id == config_id),
            key=lambda run: run.block,
        )
        for run, color in zip(group, colors, strict=True):
            axis.plot(
                [0, 1],
                [run.graph_50_cold_p50_ms, run.graph_50_warm_p50_ms],
                marker="o",
                color=color,
                alpha=0.78,
                linewidth=1.7,
                label=f"Block {run.block}",
            )
        axis.set_yscale("log")
        axis.set_xticks([0, 1], ["New WebView", "Existing WebView"])
        axis.set_title(CONFIG_LABELS[config_id], loc="left", fontweight="bold")
        axis.grid(axis="y")
    axes[0, 0].set_ylabel("Per-run median latency (ms, log scale)")
    axes[1, 0].set_ylabel("Per-run median latency (ms, log scale)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    figure.legend(
        handles,
        labels,
        frameon=False,
        ncol=4,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.955),
    )
    figure.suptitle(
        "50-node graph: paired WebView construction and reuse",
        fontweight="bold",
        y=0.995,
    )
    figure.tight_layout(rect=(0.0, 0.0, 1.0, 0.90))
    save_figure(figure, "webview_reuse_paired")


def plot_factorial_interaction(runs: list[RunSummary]) -> None:
    metrics = (
        ("cold_start_p50_ms", "Application cold start"),
        ("graph_50_cold_p50_ms", "50-node new WebView"),
    )
    figure, axes = plt.subplots(1, 2, figsize=(9.5, 4.3))
    for axis, (metric, title) in zip(axes, metrics, strict=True):
        for cpu, color in ((2, "#2E5EAA"), (4, "#146C73")):
            medians = []
            lower = []
            upper = []
            for ram in (2048, 6144):
                values = [
                    float(getattr(run, metric))
                    for run in runs
                    if run.cpu_cores == cpu and run.ram_mb == ram
                ]
                median = statistics.median(values)
                q1, q3 = quartiles(values)
                medians.append(median)
                lower.append(median - q1)
                upper.append(q3 - median)
            axis.errorbar(
                [2, 6],
                medians,
                yerr=[lower, upper],
                color=color,
                marker="o",
                linewidth=2,
                capsize=4,
                label=f"{cpu} CPU cores",
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Emulated RAM (GiB)")
        axis.set_ylabel("Median of per-run medians (ms)")
        axis.set_xticks([2, 6])
        axis.grid(axis="y")
        axis.legend(frameon=False)
    figure.tight_layout()
    save_figure(figure, "factorial_interaction")


def plot_graph_scaling(node_rows: list[dict[str, object]]) -> None:
    figure, axes = plt.subplots(1, 2, figsize=(10.2, 4.4))
    colors = ["#2E5EAA", "#D49A2A", "#146C73", "#8E5BA6"]
    phases = (
        ("cold_webview", "New WebView"),
        ("warm_update", "Existing WebView"),
    )
    for axis, (phase, title) in zip(axes, phases, strict=True):
        for config_id, color in zip(CONFIG_ORDER, colors, strict=True):
            group = [
                row for row in node_rows if row["config_id"] == config_id and row["phase"] == phase
            ]
            group.sort(key=lambda row: int(row["node_count"]))
            axis.plot(
                [int(row["node_count"]) for row in group],
                [float(row["median_of_run_medians_ms"]) for row in group],
                marker="o",
                color=color,
                linewidth=1.8,
                label=CONFIG_LABELS[config_id],
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Graph nodes")
        axis.set_ylabel("Median latency (ms)")
        axis.set_xticks(NODE_COUNTS)
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
    save_figure(figure, "graph_scaling")


def plot_run_distributions(runs: list[RunSummary]) -> None:
    metrics = (
        ("cold_start_p50_ms", "Application cold start"),
        ("warm_resume_p50_ms", "Task foreground / resume"),
        ("graph_50_select_p50_ms", "50-node selection callback"),
    )
    figure, axes = plt.subplots(1, 3, figsize=(12.2, 4.3))
    colors = ["#2E5EAA", "#D49A2A", "#146C73", "#8E5BA6"]
    for axis, (metric, title) in zip(axes, metrics, strict=True):
        groups = [
            [float(getattr(run, metric)) for run in runs if run.config_id == config_id]
            for config_id in CONFIG_ORDER
        ]
        boxes = axis.boxplot(
            groups,
            patch_artist=True,
            widths=0.55,
            showfliers=False,
        )
        for patch, color in zip(boxes["boxes"], colors, strict=True):
            patch.set_facecolor(color)
            patch.set_alpha(0.30)
            patch.set_edgecolor(color)
        for position, values, color in zip(
            range(1, 5),
            groups,
            colors,
            strict=True,
        ):
            offsets = (-0.09, -0.03, 0.03, 0.09)
            axis.scatter(
                [position + offset for offset in offsets],
                values,
                color=color,
                s=28,
                zorder=3,
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_ylabel("Per-run median latency (ms)")
        axis.set_xticks(
            range(1, 5),
            ["2c/2G", "2c/6G", "4c/2G", "4c/6G"],
        )
        axis.grid(axis="y")
    figure.tight_layout()
    save_figure(figure, "run_latency_distributions")


def write_readme(
    runs: list[RunSummary],
    config_rows: list[dict[str, object]],
    effect_rows: list[dict[str, object]],
) -> None:
    config_table = "\n".join(
        "| {cpu} | {ram} | {runs} | {success}/{samples} | {cold:.1f} | "
        "{graph:.1f} | {warm:.1f} | {ratio:.1f}x |".format(
            cpu=row["cpu_cores"],
            ram=int(row["ram_mb"]) // 1024,
            runs=row["independent_runs"],
            success=row["successful_samples"],
            samples=row["controlled_samples"],
            cold=float(row["cold_start_p50_ms_median"]),
            graph=float(row["graph_50_cold_p50_ms_median"]),
            warm=float(row["graph_50_warm_p50_ms_median"]),
            ratio=float(row["graph_50_reuse_ratio_median"]),
        )
        for row in config_rows
    )
    effect_table = "\n".join(
        "| {metric} | {factor} | {effect:+.1f}% | [{q1:+.1f}%, {q3:+.1f}%] |".format(
            metric=row["metric_label"],
            factor=row["factor"],
            effect=float(row["median_percent_change"]),
            q1=float(row["q1_percent_change"]),
            q3=float(row["q3_percent_change"]),
        )
        for row in effect_rows
        if row["factor"] in {"CPU", "RAM"}
    )
    config_table_header = (
        "| CPU cores | RAM (GiB) | Independent sessions | Successful samples | "
        "Cold start median (ms) | 50-node new WebView (ms) | "
        "50-node reused WebView (ms) | Construction/reuse ratio |"
    )
    total_samples = sum(run.controlled_samples for run in runs)
    successful_samples = sum(run.successful_samples for run in runs)
    content = f"""# Android CPU x RAM factorial evaluation

This evaluation isolates emulated CPU and RAM while keeping Android 14/API 34,
the Pixel 6 device profile, the Google APIs x86_64 system image, screen size,
density, application heap, build, host, and measurement code fixed. It uses a
2x2 factorial design with four counterbalanced blocks. Every session starts
from a wiped-data cold boot.

The independent unit is one emulator session. Each session contains 810
repeated controlled samples, but those samples are not treated as 810
independent devices. The analysis uses per-session medians and summarizes the
four independent values in each factorial cell. Exact finite bootstrap
intervals enumerate every resample of the four session summaries.

Across all sessions, {successful_samples}/{total_samples} controlled samples
met their predefined success conditions. Each configuration also passed eleven
functional graph and app-flow tests during its first block.

{config_table_header}
|---:|---:|---:|---:|---:|---:|---:|---:|
{config_table}

Factor effects below are block-level percentage changes. Negative values mean
lower latency at the higher factor level. With four blocks, they are
descriptive estimates and are not presented as population-level significance
tests.

| Metric | Factor | Median block change | Block IQR |
|---|---|---:|---:|
{effect_table}

The experiment excludes backend, retrieval, model, and recommendation quality.
New-WebView readiness records the expected DOM nodes and renderer marker; it
does not claim convergence of the force simulation. Emulator results on one
host establish controlled implementation behavior and repeatability within
the tested resource range. They do not represent the distribution of physical
Android devices.

## Reproduction

```bash
tools/evaluation/run_android_factorial_evaluation.sh
uv run --script tools/evaluation/analyze_android_factorial.py
```

Raw CSV files, test outputs, emulator logs, environment records, run order, and
session manifests are retained under `raw/`.
"""
    (EVALUATION_DIR / "README.md").write_text(content, encoding="utf-8")


def main() -> None:
    design = read_json(EVALUATION_DIR / "design.json")
    runs: list[RunSummary] = []
    metadata: dict[tuple[str, int], dict[str, object]] = {}
    for config_id in CONFIG_ORDER:
        for block in range(1, 5):
            run, run_metadata = validate_run(config_id, block)
            runs.append(run)
            metadata[(config_id, block)] = run_metadata

    positions = {
        config_id: sorted(run.sequence_position for run in runs if run.config_id == config_id)
        for config_id in CONFIG_ORDER
    }
    if any(value != [1, 2, 3, 4] for value in positions.values()):
        raise ValueError(f"Sequence positions are not counterbalanced: {positions}")

    repository_revisions = {
        str(item["run_manifest"]["repository_revision"]) for item in metadata.values()
    }
    if len(repository_revisions) != 1:
        raise ValueError(f"Multiple repository revisions were measured: {repository_revisions}")
    max_heap_values = {int(item["environment"]["max_heap_bytes"]) for item in metadata.values()}
    if len(max_heap_values) != 1:
        raise ValueError(f"Application heap changed across sessions: {max_heap_values}")

    run_rows = [
        asdict(run)
        for run in sorted(
            runs,
            key=lambda item: (item.block, item.sequence_position),
        )
    ]
    config_rows = configuration_summaries(runs)
    effect_rows = factor_effects(runs)
    node_rows = node_summaries(metadata)
    write_rows(EVALUATION_DIR / "run_summary.csv", run_rows)
    write_rows(EVALUATION_DIR / "configuration_summary.csv", config_rows)
    write_rows(EVALUATION_DIR / "factor_effects.csv", effect_rows)
    write_rows(EVALUATION_DIR / "graph_node_summary.csv", node_rows)

    payload = {
        "schema_version": "android-factorial-summary-v1",
        "design": design,
        "method": {
            "independent_unit": "cold-boot wiped-data emulator session",
            "independent_blocks": 4,
            "factorial_cells": 4,
            "controlled_samples_per_session": 810,
            "within_session_p50": "sample median",
            "within_session_p95": "nearest-rank percentile",
            "across_session_interval": (
                "exact finite bootstrap 95% interval of four per-session medians"
            ),
            "inferential_p_values_reported": False,
            "external_backend_used": False,
        },
        "audit": {
            "repository_revisions": sorted(repository_revisions),
            "application_max_heap_bytes": sorted(max_heap_values),
            "total_controlled_samples": sum(run.controlled_samples for run in runs),
            "successful_controlled_samples": sum(run.successful_samples for run in runs),
            "functional_tests": sum(run.functional_tests for run in runs),
            "measurement_tests": sum(run.measurement_tests for run in runs),
            "credentials_retained": False,
        },
        "run_results": run_rows,
        "configuration_results": config_rows,
        "factor_effects": effect_rows,
        "graph_node_results": node_rows,
    }
    (EVALUATION_DIR / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    configure_plots()
    plot_webview_reuse(runs)
    plot_factorial_interaction(runs)
    plot_graph_scaling(node_rows)
    plot_run_distributions(runs)
    write_readme(runs, config_rows, effect_rows)
    print(
        f"Validated {len(runs)} independent sessions and "
        f"{sum(run.controlled_samples for run in runs)} controlled samples.",
    )


if __name__ == "__main__":
    main()
