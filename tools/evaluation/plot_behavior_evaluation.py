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
from pathlib import Path

import matplotlib.pyplot as plt

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plot recorded behavior evaluation summaries.")
    parser.add_argument(
        "--evaluation-dir",
        type=Path,
        default=DEFAULT_EVALUATION_DIR,
        help="directory containing summary.json and raw/case_results.jsonl",
    )
    return parser


def load_artifacts(evaluation_dir: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    summary_path = evaluation_dir / "summary.json"
    cases_path = evaluation_dir / "raw/case_results.jsonl"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines()]
    if summary.get("schema_version") != "behavior-evaluation-summary-v1":
        raise ValueError("Unsupported behavior summary schema.")
    if summary.get("controlled_synthetic") is not True:
        raise ValueError("Behavior figures require a controlled synthetic run.")
    if summary.get("invariant_failures"):
        raise ValueError("Behavior figures refuse runs with invariant failures.")
    return summary, cases


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
    figure, axis = plt.subplots(figsize=(9.4, 4.8))
    for model_index, model_id in enumerate(HEADLINE_MODELS):
        offset = (model_index - 1.5) * width
        values = [float(lookup[(model_id, metric)]) for metric, _ in metrics]
        bars = axis.bar(
            [position + offset for position in x_positions],
            values,
            width=width,
            color=MODEL_COLORS[model_id],
            label=MODEL_LABELS[model_id],
        )
        axis.bar_label(bars, fmt="%.3f", fontsize=7.5, padding=2, rotation=90)
    axis.set_xticks(list(x_positions), [label for _, label in metrics])
    axis.set_ylim(0, 1.12)
    axis.set_ylabel("Macro mean across applicable controlled cases")
    axis.set_title("Controlled ranking comparison", loc="left", fontweight="bold")
    axis.text(
        0,
        1.02,
        "Undefined cold-start relevance metrics are excluded, not treated as zero.",
        transform=axis.transAxes,
        color=MUTED,
        fontsize=8.5,
    )
    axis.grid(axis="y")
    axis.legend(frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.13))
    figure.subplots_adjust(bottom=0.24, top=0.86, left=0.1, right=0.98)
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
    figure, axes = plt.subplots(1, 2, figsize=(10.2, 4.8), sharex=False)
    colors = (BLUE, TEAL, GOLD, CORAL, PURPLE)
    for axis, pair_id, title in zip(
        axes,
        pair_ids,
        ("Recent interest shift", "Exposed negative feedback"),
        strict=True,
    ):
        values = [float(lookup[(pair_id, model)]) for model in models]
        positions = list(range(len(models)))
        bars = axis.barh(positions, values, color=colors)
        axis.axvline(0, color=INK, linewidth=0.9)
        axis.set_yticks(positions, [MODEL_LABELS[model] for model in models])
        axis.invert_yaxis()
        axis.set_xlabel("Target score after minus before")
        axis.set_title(title, loc="left", fontweight="bold")
        axis.grid(axis="x")
        axis.bar_label(bars, fmt="%+.3f", fontsize=8, padding=3)
    figure.suptitle(
        "Mechanism response on paired controlled traces",
        x=0.08,
        y=0.98,
        ha="left",
        fontsize=12,
        fontweight="bold",
        color=INK,
    )
    figure.subplots_adjust(top=0.82, bottom=0.15, left=0.19, right=0.98, wspace=0.48)
    save_figure(figure, figure_dir, "mechanism_deltas")


def save_figure(figure: object, figure_dir: Path, stem: str) -> None:
    figure_dir.mkdir(parents=True, exist_ok=True)
    figure.savefig(figure_dir / f"{stem}.png", dpi=220, bbox_inches="tight")
    figure.savefig(figure_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    arguments = build_parser().parse_args()
    summary, cases = load_artifacts(arguments.evaluation_dir)
    if not cases:
        raise ValueError("Behavior case results cannot be empty.")
    configure_plots()
    figure_dir = arguments.evaluation_dir / "figures"
    plot_ranking_comparison(summary, figure_dir)
    plot_mechanism_deltas(summary, figure_dir)
    print(f"Behavior figures written to {figure_dir}")


if __name__ == "__main__":
    main()
