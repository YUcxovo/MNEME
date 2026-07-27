#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "matplotlib==3.10.3",
# ]
# ///
"""Render thesis-ready figures from recorded behavior evaluation artifacts."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "mneme-matplotlib"))

import matplotlib.pyplot as plt
from matplotlib.figure import Figure

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EVALUATION_DIR = REPO_ROOT / "docs/evaluation/behavior"

INK = "#1F2D36"
MUTED = "#65757F"
GRID = "#DCE4E7"
BLUE = "#2E5EAA"
TEAL = "#147D7E"
GOLD = "#D49A2A"
CORAL = "#C95C54"
PURPLE = "#7253A6"

HEADLINE_MODELS = ("recency-only", "explicit-recency", "behavior-v1", "behavior-v2")
MODEL_LABELS = {
    "recency-only": "Recency only",
    "explicit-recency": "Explicit + recency",
    "behavior-v1": "Behavior v1",
    "behavior-v2": "Behavior v2",
    "v2-no-exposure-gate": "No exposure gate",
    "v2-no-negative-channel": "No negative channel",
    "v2-no-confidence-gate": "No confidence gate",
    "v2-no-saturation": "No saturation",
    "v2-single-timescale": "Single timescale",
}
MODEL_COLORS = {
    "recency-only": MUTED,
    "explicit-recency": GOLD,
    "behavior-v1": BLUE,
    "behavior-v2": TEAL,
}
MODEL_HATCHES = {
    "recency-only": "",
    "explicit-recency": "//",
    "behavior-v1": "xx",
    "behavior-v2": "..",
    "v2-no-exposure-gate": "//",
    "v2-no-negative-channel": "\\\\",
    "v2-no-confidence-gate": "++",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot recorded behavior evaluation summaries.")
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=DEFAULT_EVALUATION_DIR,
        help="directory containing summary.json and raw/case_results.jsonl",
    )
    return parser


def load_artifacts(
    evaluation_dir: Path,
) -> tuple[dict[str, object], list[dict[str, object]], dict[str, object]]:
    summary_path = evaluation_dir / "summary.json"
    cases_path = evaluation_dir / "raw/case_results.jsonl"
    performance_path = evaluation_dir / "performance.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines()]
    performance = json.loads(performance_path.read_text(encoding="utf-8"))
    if summary.get("schema_version") != "behavior-evaluation-summary-v1":
        raise ValueError("Unsupported behavior summary schema.")
    if summary.get("controlled_synthetic") is not True:
        raise ValueError("Behavior figures require a controlled synthetic run.")
    if summary.get("invariant_failures"):
        raise ValueError("Behavior figures refuse runs with invariant failures.")
    if performance.get("schema_version") != "behavior-performance-artifact-v1":
        raise ValueError("Unsupported behavior performance schema.")
    benchmark = performance.get("benchmark")
    if not isinstance(benchmark, dict) or benchmark.get("environment_sensitive") is not True:
        raise ValueError("Behavior performance figures require environment-sensitive metadata.")
    return summary, cases, performance


def configure_plots() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.5,
            "axes.edgecolor": GRID,
            "axes.labelcolor": INK,
            "axes.titlecolor": INK,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": INK,
            "ytick.color": INK,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "grid.color": GRID,
            "grid.linewidth": 0.7,
        }
    )


def plot_ranking_comparison(summary: dict[str, object], figure_dir: Path) -> None:
    aggregates = summary["aggregates"]
    assert isinstance(aggregates, list)
    lookup = {
        (row["model_id"], row["metric"]): row["mean"]
        for row in aggregates
        if row["scenario_family"] is None
    }
    metrics = (
        ("ndcg_at_k", "nDCG@5"),
        ("recall_at_k", "Recall@5"),
        ("reciprocal_rank", "Reciprocal rank"),
    )
    x_positions = range(len(metrics))
    width = 0.18
    figure, axis = plt.subplots(figsize=(7.2, 4.6))
    for model_index, model_id in enumerate(HEADLINE_MODELS):
        offset = (model_index - 1.5) * width
        values = [float(lookup[(model_id, metric)]) for metric, _ in metrics]
        bars = axis.bar(
            [position + offset for position in x_positions],
            values,
            width=width,
            color=MODEL_COLORS[model_id],
            edgecolor="white",
            hatch=MODEL_HATCHES[model_id],
            linewidth=0.7,
            label=MODEL_LABELS[model_id],
        )
        axis.bar_label(bars, fmt="%.3f", fontsize=7.5, padding=2, rotation=90)
    axis.set_xticks(list(x_positions), [label for _, label in metrics])
    axis.set_ylim(0, 1.12)
    axis.set_ylabel("Macro mean (applicable controlled cases)")
    figure.suptitle(
        "Controlled ranking comparison",
        x=0.1,
        y=0.98,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    figure.text(
        0.1,
        0.91,
        "Undefined cold-start relevance metrics are excluded, not treated as zero.",
        color=MUTED,
        fontsize=8.5,
    )
    axis.grid(axis="y")
    axis.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    figure.subplots_adjust(bottom=0.24, top=0.84, left=0.1, right=0.98)
    save_figure(figure, figure_dir, "ranking_comparison")


def plot_mechanism_deltas(summary: dict[str, object], figure_dir: Path) -> None:
    rows = summary["mechanism_deltas"]
    assert isinstance(rows, list)
    pair_ids = ("interest-shift-01", "exposed-negative-01")
    models = (
        "behavior-v1",
        "behavior-v2",
        "v2-no-exposure-gate",
        "v2-no-negative-channel",
        "v2-no-confidence-gate",
    )
    lookup = {(row["pair_id"], row["model_id"]): row["target_score_delta"] for row in rows}
    figure, axes = plt.subplots(2, 1, figsize=(7.2, 7.4), sharex=False)
    colors = (BLUE, TEAL, GOLD, CORAL, PURPLE)
    desired_directions = (
        "Higher is the expected response",
        "Lower is the expected response",
    )
    for axis, pair_id, title, desired_direction in zip(
        axes,
        pair_ids,
        ("Recent interest shift", "Exposed negative feedback"),
        desired_directions,
        strict=True,
    ):
        values = [float(lookup[(pair_id, model)]) for model in models]
        positions = list(range(len(models)))
        bars = axis.barh(
            positions,
            values,
            color=colors,
            edgecolor="white",
            hatch=[MODEL_HATCHES.get(model, "") for model in models],
            linewidth=0.7,
        )
        axis.axvline(0, color=INK, linewidth=0.9)
        axis.set_yticks(
            positions,
            [MODEL_LABELS[model] for model in models],
            fontsize=8.5,
        )
        axis.invert_yaxis()
        axis.set_xlabel("Target score after minus before")
        axis.set_title(title, loc="left", fontweight="bold")
        axis.text(
            1,
            1.03,
            desired_direction,
            transform=axis.transAxes,
            ha="right",
            color=MUTED,
            fontsize=8,
        )
        axis.grid(axis="x")
        minimum = min(0.0, *values)
        maximum = max(0.0, *values)
        span = max(maximum - minimum, 0.1)
        axis.set_xlim(minimum - 0.14 * span, maximum + 0.14 * span)
        for bar, value in zip(bars, values, strict=True):
            if value < 0 and abs(value) >= 0.08:
                label_x = value + 0.012 * span
                label_alignment = "left"
                label_color = "white"
            else:
                label_x = value + (0.012 * span if value >= 0 else -0.012 * span)
                label_alignment = "left" if value >= 0 else "right"
                label_color = INK
            axis.text(
                label_x,
                bar.get_y() + bar.get_height() / 2,
                f"{value:+.3f}",
                va="center",
                ha=label_alignment,
                color=label_color,
                fontsize=8,
            )
    figure.suptitle(
        "Mechanism response on paired controlled traces",
        x=0.08,
        y=0.98,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    figure.subplots_adjust(top=0.9, bottom=0.08, left=0.28, right=0.98, hspace=0.55)
    save_figure(figure, figure_dir, "mechanism_deltas")


def plot_performance_scaling(performance: dict[str, object], figure_dir: Path) -> None:
    benchmark = performance["benchmark"]
    assert isinstance(benchmark, dict)
    rows = benchmark["cases"]
    assert isinstance(rows, list)
    repetitions = int(benchmark["measured_repetitions"])
    figure, axes = plt.subplots(2, 1, figsize=(7.2, 6.8))
    operations = (
        ("aggregation", "Profile aggregation", "signal_count", "Events"),
        ("ranking", "Candidate ranking", "candidate_count", "Candidates"),
    )
    for axis, (operation, title, count_key, count_label) in zip(axes, operations, strict=True):
        labels = [f"{row['scale_id']}\n{count_label}: {row[count_key]}" for row in rows]
        median = [float(row[operation]["median_ms"]) for row in rows]
        p95 = [float(row[operation]["p95_ms"]) for row in rows]
        positions = list(range(len(rows)))
        axis.plot(
            positions,
            median,
            color=TEAL,
            marker="o",
            linewidth=2,
            label="Median",
        )
        axis.plot(
            positions,
            p95,
            color=BLUE,
            marker="s",
            linestyle="--",
            linewidth=1.6,
            label="p95",
        )
        axis.set_xticks(positions, labels)
        axis.set_yscale("log")
        axis.set_ylabel("Latency (ms, log scale)")
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(axis="y", which="both")
        axis.legend(frameon=False, loc="upper left")
        for position, value in zip(positions, median, strict=True):
            axis.annotate(
                f"{value:.2f} ms",
                (position, value),
                xytext=(7, -2),
                textcoords="offset points",
                fontsize=8,
                color=INK,
            )
    figure.suptitle(
        "Behavior-v2 in-process performance",
        x=0.11,
        y=0.98,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    figure.text(
        0.11,
        0.935,
        f"1536-dimensional vectors; {repetitions} measured repetitions after warm-up.",
        color=MUTED,
        fontsize=8.5,
    )
    figure.subplots_adjust(top=0.88, bottom=0.09, left=0.12, right=0.98, hspace=0.45)
    save_figure(figure, figure_dir, "performance_scaling")


def save_figure(figure: Figure, figure_dir: Path, stem: str) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(figure_dir / f"{stem}.png", dpi=220, bbox_inches="tight")
    figure.savefig(figure_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    arguments = build_parser().parse_args()
    summary, cases, performance = load_artifacts(arguments.evaluation_dir)
    if not cases:
        raise ValueError("Behavior case results cannot be empty.")
    configure_plots()
    figure_dir = arguments.evaluation_dir / "figures"
    plot_ranking_comparison(summary, figure_dir)
    plot_mechanism_deltas(summary, figure_dir)
    plot_performance_scaling(performance, figure_dir)
    print(f"Behavior figures written to {figure_dir}")


if __name__ == "__main__":
    main()
