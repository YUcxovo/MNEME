#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "matplotlib==3.10.3",
# ]
# ///
"""Validate, summarize, and plot the Android E4 measurement artifacts."""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Iterable

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation" / "e4"
RAW_DIR = EVALUATION_DIR / "raw"
FIGURE_DIR = EVALUATION_DIR / "figures"

TEAL = "#146C73"
BLUE = "#2E5EAA"
GOLD = "#D49A2A"
CORAL = "#C95C54"
INK = "#20303C"
MUTED = "#6B7B86"
PALE = "#EFF5F4"


@dataclass(frozen=True)
class Summary:
    track: str
    scenario: str
    condition: str
    n: int
    success_count: int
    success_rate: float
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float


def read_csv(file_name: str) -> list[dict[str, str]]:
    path = RAW_DIR / file_name
    if not path.is_file():
        raise FileNotFoundError(f"Missing required E4 artifact: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(file_name: str) -> dict[str, object]:
    path = RAW_DIR / file_name
    if not path.is_file():
        raise FileNotFoundError(f"Missing required E4 artifact: {path}")
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
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def summarize(
    rows: Iterable[dict[str, str]],
    *,
    track: str,
    scenario_key: Callable[[dict[str, str]], str],
    condition_key: Callable[[dict[str, str]], str],
    duration_key: str,
) -> list[Summary]:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        groups[(scenario_key(row), condition_key(row))].append(row)

    summaries: list[Summary] = []
    for (scenario, condition), group in sorted(groups.items()):
        durations = [float(row[duration_key]) for row in group]
        successes = sum(as_success(row["success"]) for row in group)
        summaries.append(
            Summary(
                track=track,
                scenario=scenario,
                condition=condition,
                n=len(group),
                success_count=successes,
                success_rate=successes / len(group),
                p50_ms=statistics.median(durations),
                p95_ms=nearest_rank(durations, 0.95),
                min_ms=min(durations),
                max_ms=max(durations),
            ),
        )
    return summaries


def validate_counts(
    rows: list[dict[str, str]],
    *,
    file_name: str,
    expected: dict[tuple[str, ...], int],
    keys: tuple[str, ...],
) -> None:
    observed: dict[tuple[str, ...], int] = defaultdict(int)
    for row in rows:
        observed[tuple(row[key] for key in keys)] += 1
    if observed != expected:
        raise ValueError(
            f"{file_name} has unexpected sample groups.\n"
            f"Expected: {dict(expected)}\nObserved: {dict(observed)}",
        )


def write_summary(
    summaries: list[Summary],
    environment: dict[str, object],
    manifest: dict[str, object],
    live_rows: list[dict[str, str]],
) -> None:
    live_readbacks = [
        row for row in live_rows if row["scenario"] == "live_client_readback"
    ]
    payload = {
        "schema_version": "e4-android-summary-v1",
        "method": {
            "latency_unit": "milliseconds",
            "p50": "sample median",
            "p95": "nearest-rank percentile",
            "controlled_and_live_results_are_reported_separately": True,
        },
        "environment": environment,
        "run_manifest": manifest,
        "live_readback": {
            "digest_entry_counts": sorted(
                {int(row["digest_entries"]) for row in live_readbacks}
            ),
            "preference_model_versions": sorted(
                {int(row["preference_model_version"]) for row in live_readbacks}
            ),
            "briefing_origins": sorted(
                {row["briefing_origin"] for row in live_readbacks}
            ),
        },
        "results": [asdict(item) for item in summaries],
    }
    (EVALUATION_DIR / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with (EVALUATION_DIR / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=list(asdict(summaries[0])))
        writer.writeheader()
        for item in summaries:
            writer.writerow(asdict(item))


def configure_plots() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.edgecolor": "#A8B4BA",
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": INK,
            "ytick.color": INK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "grid.color": "#DDE5E7",
            "grid.linewidth": 0.7,
        },
    )


def result_lookup(summaries: list[Summary]) -> dict[tuple[str, str, str], Summary]:
    return {(item.track, item.scenario, item.condition): item for item in summaries}


def plot_graph_latency(summaries: list[Summary]) -> None:
    lookup = result_lookup(summaries)
    node_counts = [1, 12, 25, 50]
    phases = [
        ("cold_webview", "New WebView", BLUE),
        ("warm_update", "Existing WebView", TEAL),
    ]
    scenarios = [
        ("render_ready", "DOM ready"),
        ("select_node", "Selection callback"),
    ]
    figure, axes = plt.subplots(1, 2, figsize=(9.2, 3.55), constrained_layout=True)
    for axis, (scenario, title) in zip(axes, scenarios, strict=True):
        for phase, label, color in phases:
            points = [
                lookup[("graph", scenario, f"{phase}; nodes={count}")].p50_ms
                for count in node_counts
            ]
            tails = [
                lookup[("graph", scenario, f"{phase}; nodes={count}")].p95_ms
                for count in node_counts
            ]
            axis.plot(
                node_counts,
                points,
                color=color,
                marker="o",
                linewidth=2,
                label=f"{label} p50",
            )
            axis.plot(
                node_counts,
                tails,
                color=color,
                marker=".",
                linewidth=1.2,
                linestyle="--",
                alpha=0.72,
                label=f"{label} p95",
            )
        axis.set_title(title, loc="left", fontweight="bold")
        axis.set_xlabel("Graph nodes")
        axis.set_ylabel("Latency (ms)")
        axis.set_xticks(node_counts)
        axis.grid(axis="y")
    axes[0].legend(frameon=False, fontsize=8)
    figure.suptitle(
        "Android citation-graph renderer and selection latency",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
        color=INK,
    )
    save_figure(figure, "graph_latency")


def plot_mobile_reliability(summaries: list[Summary]) -> None:
    lookup = result_lookup(summaries)
    left_items = [
        ("startup", "cold_process", "", "Cold process start"),
        ("startup", "warm_task_resume", "", "Warm task resume"),
        ("state", "cached_warm_start", "", "Cached briefing restore"),
        (
            "state",
            "cached_offline_disclosure",
            "",
            "Offline cache disclosure",
        ),
        (
            "state",
            "cached_server_failure_disclosure",
            "",
            "Server-failure disclosure",
        ),
        ("state", "invalid_cache_error", "", "Invalid-cache error state"),
        ("state", "three_stage_job_polling", "", "Three-stage job polling"),
    ]
    right_items = [
        ("event_sync", "queue_write", "controlled", "Queue three events"),
        (
            "event_sync",
            "retryable_http_failure",
            "controlled",
            "Controlled HTTP 503",
        ),
        ("event_sync", "retry_success", "controlled", "Controlled retry"),
        (
            "event_sync",
            "duplicate_replay",
            "controlled",
            "Controlled duplicate",
        ),
        (
            "event_sync",
            "live_retry_upload",
            "live_backend",
            "Live backend upload",
        ),
        (
            "event_sync",
            "live_duplicate_replay",
            "live_backend",
            "Live duplicate replay",
        ),
        (
            "event_sync",
            "live_client_readback",
            "live_backend",
            "Live client readback",
        ),
    ]
    figure, axes = plt.subplots(1, 2, figsize=(10.2, 4.6), constrained_layout=True)
    plot_latency_list(axes[0], lookup, left_items, "Mobile state resolution")
    plot_latency_list(axes[1], lookup, right_items, "Event synchronization")
    figure.suptitle(
        "Measured Android client reliability paths",
        x=0.01,
        ha="left",
        fontsize=13,
        fontweight="bold",
        color=INK,
    )
    save_figure(figure, "mobile_reliability")


def plot_latency_list(
    axis: plt.Axes,
    lookup: dict[tuple[str, str, str], Summary],
    items: list[tuple[str, str, str, str]],
    title: str,
) -> None:
    results = [lookup[item[:3]] for item in items]
    labels = [item[3] for item in items]
    positions = list(range(len(items)))
    p50 = [item.p50_ms for item in results]
    p95 = [item.p95_ms for item in results]
    axis.hlines(positions, p50, p95, color="#B7C5C9", linewidth=3)
    axis.scatter(p95, positions, color=GOLD, s=34, label="p95", zorder=3)
    axis.scatter(p50, positions, color=TEAL, s=40, label="p50", zorder=4)
    axis.set_yticks(positions, labels)
    axis.invert_yaxis()
    axis.set_xscale("symlog", linthresh=1)
    axis.set_xlabel("Latency (ms, symlog scale)")
    axis.set_title(title, loc="left", fontweight="bold")
    axis.grid(axis="x")
    axis.legend(frameon=False, loc="lower right")
    for position, result in zip(positions, results, strict=True):
        axis.annotate(
            f"{result.success_count}/{result.n}",
            (result.p95_ms, position),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            color=MUTED,
            fontsize=7.5,
        )


def plot_client_loop() -> None:
    figure, axis = plt.subplots(figsize=(10.2, 4.25))
    axis.set_xlim(0, 12)
    axis.set_ylim(0, 5.5)
    axis.axis("off")

    boxes = [
        (
            0.35,
            3.05,
            2.25,
            1.25,
            "Visible Android UI",
            "Briefing, paper, Q&A,\ngraph selection",
        ),
        (
            3.25,
            3.05,
            2.25,
            1.25,
            "Client state",
            "ViewModel states and\ntruthful source disclosure",
        ),
        (
            6.15,
            3.05,
            2.25,
            1.25,
            "Durable client data",
            "Room cache and\npending event queue",
        ),
        (
            9.05,
            3.05,
            2.25,
            1.25,
            "Backend contract",
            "REST resources, jobs,\nevent ingestion",
        ),
        (
            6.15,
            0.75,
            2.25,
            1.15,
            "Failure handling",
            "Cache retention,\nretry and deduplication",
        ),
        (
            3.25,
            0.75,
            2.25,
            1.15,
            "Returned content",
            "Live or cached model\nrendered by the UI",
        ),
    ]
    for index, (x, y, width, height, title, body) in enumerate(boxes):
        color = [BLUE, TEAL, GOLD, CORAL, GOLD, TEAL][index]
        add_box(axis, x, y, width, height, title, body, color)

    arrows = [
        ((2.6, 3.68), (3.25, 3.68)),
        ((5.5, 3.68), (6.15, 3.68)),
        ((8.4, 3.68), (9.05, 3.68)),
        ((10.18, 3.05), (8.38, 1.9)),
        ((6.15, 1.32), (5.5, 1.32)),
        ((3.25, 1.32), (1.55, 3.05)),
        ((7.28, 3.05), (7.28, 1.9)),
    ]
    for start, end in arrows:
        axis.add_patch(
            FancyArrowPatch(
                start,
                end,
                arrowstyle="-|>",
                mutation_scale=13,
                linewidth=1.7,
                color=MUTED,
                connectionstyle="arc3,rad=0.0",
            ),
        )

    axis.text(
        0.35,
        5.1,
        "Android client state and event loop evaluated in E4",
        color=INK,
        fontsize=14,
        fontweight="bold",
        va="top",
    )
    axis.text(
        0.35,
        4.7,
        "Solid paths are implemented client behavior; recommendation and graph-algorithm quality are outside this evaluation.",
        color=MUTED,
        fontsize=9,
        va="top",
    )
    save_figure(figure, "android_client_loop")


def add_box(
    axis: plt.Axes,
    x: float,
    y: float,
    width: float,
    height: float,
    title: str,
    body: str,
    color: str,
) -> None:
    axis.add_patch(
        FancyBboxPatch(
            (x, y),
            width,
            height,
            boxstyle="round,pad=0.04,rounding_size=0.12",
            linewidth=1.7,
            edgecolor=color,
            facecolor=PALE,
        ),
    )
    axis.text(
        x + 0.16,
        y + height - 0.27,
        title,
        color=color,
        fontsize=10,
        fontweight="bold",
        va="top",
    )
    axis.text(
        x + 0.16,
        y + height - 0.57,
        body,
        color=INK,
        fontsize=8.4,
        va="top",
        linespacing=1.25,
    )


def save_figure(figure: plt.Figure, stem: str) -> None:
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(FIGURE_DIR / f"{stem}.pdf", bbox_inches="tight")
    figure.savefig(FIGURE_DIR / f"{stem}.png", dpi=220, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    startup_rows = read_csv("app_start_measurements.csv")
    state_rows = read_csv("state_measurements.csv")
    graph_rows = read_csv("graph_measurements.csv")
    graph_state_rows = read_csv("graph_state_measurements.csv")
    event_rows = read_csv("event_sync_measurements.csv")
    live_rows = read_csv("live_event_closed_loop.csv")
    environment = read_json("environment.json")
    manifest = read_json("run_manifest.json")

    validate_counts(
        startup_rows,
        file_name="app_start_measurements.csv",
        keys=("scenario",),
        expected={("cold_process",): 20, ("warm_task_resume",): 20},
    )
    validate_counts(
        state_rows,
        file_name="state_measurements.csv",
        keys=("scenario",),
        expected={
            ("live_seed",): 30,
            ("cached_warm_start",): 30,
            ("cached_offline_disclosure",): 30,
            ("cached_server_failure_disclosure",): 30,
            ("invalid_cache_error",): 30,
            ("three_stage_job_polling",): 10,
        },
    )
    validate_counts(
        graph_rows,
        file_name="graph_measurements.csv",
        keys=("scenario", "phase", "node_count"),
        expected={
            (scenario, phase, str(node_count)): iterations
            for scenario in ("render_ready", "select_node")
            for phase, iterations in (("cold_webview", 20), ("warm_update", 30))
            for node_count in (1, 12, 25, 50)
        },
    )
    validate_counts(
        graph_state_rows,
        file_name="graph_state_measurements.csv",
        keys=("state",),
        expected={("ready",): 30, ("fallback",): 30, ("empty",): 30},
    )
    validate_counts(
        event_rows,
        file_name="event_sync_measurements.csv",
        keys=("scenario",),
        expected={
            ("queue_write",): 30,
            ("retryable_http_failure",): 30,
            ("retry_success",): 30,
            ("duplicate_replay",): 30,
        },
    )
    validate_counts(
        live_rows,
        file_name="live_event_closed_loop.csv",
        keys=("scenario",),
        expected={
            ("live_queue_write",): 5,
            ("controlled_failure_before_live_retry",): 5,
            ("live_retry_upload",): 5,
            ("live_duplicate_replay",): 5,
            ("live_client_readback",): 5,
        },
    )

    summaries: list[Summary] = []
    summaries += summarize(
        startup_rows,
        track="startup",
        scenario_key=lambda row: row["scenario"],
        condition_key=lambda row: "",
        duration_key="wait_time_ms",
    )
    summaries += summarize(
        state_rows,
        track="state",
        scenario_key=lambda row: row["scenario"],
        condition_key=lambda row: "",
        duration_key="duration_ms",
    )
    summaries += summarize(
        graph_rows,
        track="graph",
        scenario_key=lambda row: row["scenario"],
        condition_key=lambda row: (f"{row['phase']}; nodes={row['node_count']}"),
        duration_key="duration_ms",
    )
    summaries += summarize(
        graph_state_rows,
        track="graph_state",
        scenario_key=lambda row: row["state"],
        condition_key=lambda row: "",
        duration_key="duration_ms",
    )
    summaries += summarize(
        event_rows,
        track="event_sync",
        scenario_key=lambda row: row["scenario"],
        condition_key=lambda row: "controlled",
        duration_key="duration_ms",
    )
    summaries += summarize(
        live_rows,
        track="event_sync",
        scenario_key=lambda row: row["scenario"],
        condition_key=lambda row: "live_backend",
        duration_key="duration_ms",
    )

    write_summary(summaries, environment, manifest, live_rows)
    configure_plots()
    plot_graph_latency(summaries)
    plot_mobile_reliability(summaries)
    plot_client_loop()
    print(
        f"Wrote {len(summaries)} summary groups and three figures to {EVALUATION_DIR}",
    )


if __name__ == "__main__":
    main()
