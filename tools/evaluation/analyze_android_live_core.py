#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "matplotlib==3.10.3",
# ]
# ///
"""Validate, summarize, and plot the Android live-core acceptance artifacts."""

from __future__ import annotations

import csv
import json
import math
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

import matplotlib.pyplot as plt


REPO_ROOT = Path(__file__).resolve().parents[2]
EVALUATION_DIR = REPO_ROOT / "docs" / "evaluation" / "live-core"
RAW_DIR = EVALUATION_DIR / "raw"
FIGURE_DIR = EVALUATION_DIR / "figures"

TEAL = "#146C73"
BLUE = "#2E5EAA"
GOLD = "#D49A2A"
CORAL = "#C95C54"
INK = "#20303C"
MUTED = "#6B7B86"

UI_SCENARIOS = (
    "seed_to_five_paper_briefing",
    "paper_and_summary",
    "open_paper_source",
    "free_question_and_sources",
    "citation_graph",
    "select_graph_neighbor",
    "open_selected_graph_paper",
)
REPOSITORY_SCENARIOS = (
    "live_five_paper_briefing",
    "cached_briefing_restore",
    "paper_and_summary",
    "free_question_and_sources",
    "citation_graph",
    "open_selected_graph_paper",
)
LABELS = {
    "seed_to_five_paper_briefing": "Seed to five-paper briefing",
    "live_five_paper_briefing": "Live five-paper briefing",
    "cached_briefing_restore": "Cached briefing restore",
    "paper_and_summary": "Paper and summary",
    "open_paper_source": "Open paper source",
    "free_question_and_sources": "Free question and sources",
    "open_qa_source": "Open cited source",
    "citation_graph": "Citation graph",
    "select_graph_neighbor": "Select graph neighbor",
    "open_selected_graph_paper": "Open graph paper",
}


def display_label(scenario: str, rows: list[dict[str, str]]) -> str:
    if scenario == "citation_graph":
        graph_outcomes = {
            row["outcome"] for row in rows if row["scenario"] == "citation_graph"
        }
        if graph_outcomes == {"center_only_graph"}:
            return "Graph response (center only)"
    return LABELS[scenario]


@dataclass(frozen=True)
class StageSummary:
    track: str
    scenario: str
    n: int
    success_count: int
    success_rate: float
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float


def read_csv() -> list[dict[str, str]]:
    path = RAW_DIR / "live_core_path.csv"
    if not path.is_file():
        raise FileNotFoundError(f"Missing live-core artifact: {path}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_json(file_name: str) -> dict[str, object]:
    path = RAW_DIR / file_name
    if not path.is_file():
        raise FileNotFoundError(f"Missing live-core artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def as_success(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"Unexpected success value: {value!r}")
    return normalized == "true"


def nearest_rank(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def validate_protocol(rows: list[dict[str, str]]) -> None:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["track"], row["scenario"])].append(row)

    expected = {
        **{("live_ui", scenario): 1 for scenario in UI_SCENARIOS},
        **{("live_repository", scenario): 5 for scenario in REPOSITORY_SCENARIOS},
    }
    required_observed = {
        key: len(value)
        for key, value in grouped.items()
        if key[1] not in {"iteration_completion", "open_qa_source"}
    }
    if required_observed != expected:
        raise ValueError(
            "Live-core protocol is incomplete.\n"
            f"Expected: {expected}\nObserved: {required_observed}",
        )
    optional_qa_source_rows = grouped.get(("live_ui", "open_qa_source"), [])
    if len(optional_qa_source_rows) > 1:
        raise ValueError("The optional Q&A source callback was recorded more than once.")

    for row in rows:
        if row["scenario"] in {
            "seed_to_five_paper_briefing",
            "live_five_paper_briefing",
        }:
            if int(row["paper_count"]) != 5:
                raise ValueError("A retained seed stage did not return five papers.")
        if row["scenario"] == "citation_graph" and int(row["graph_nodes"]) > 50:
            raise ValueError("A retained graph exceeded the Android request limit.")
        if row["scenario"] == "citation_graph":
            if int(row["graph_nodes"]) < 2 or int(row["graph_edges"]) < 1:
                raise ValueError("The retained product path did not reach a multi-node graph.")


def summarize(rows: list[dict[str, str]]) -> list[StageSummary]:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["track"], row["scenario"])].append(row)

    summaries = []
    for (track, scenario), group in sorted(grouped.items()):
        durations = [float(row["duration_ms"]) for row in group]
        successes = sum(as_success(row["success"]) for row in group)
        summaries.append(
            StageSummary(
                track=track,
                scenario=scenario,
                n=len(group),
                success_count=successes,
                success_rate=round(successes / len(group), 6),
                p50_ms=round(statistics.median(durations), 3),
                p95_ms=round(nearest_rank(durations, 0.95), 3),
                min_ms=round(min(durations), 3),
                max_ms=round(max(durations), 3),
            ),
        )
    return summaries


def write_results(
    rows: list[dict[str, str]],
    summaries: list[StageSummary],
    environment: dict[str, object],
    manifest: dict[str, object],
) -> None:
    qa_rows = [row for row in rows if row["scenario"] == "free_question_and_sources"]
    graph_rows = [row for row in rows if row["scenario"] == "citation_graph"]
    payload = {
        "schema_version": "live-core-android-summary-v1",
        "method": {
            "latency_unit": "milliseconds",
            "p50": "sample median",
            "p95": "nearest-rank percentile",
            "ui_timing_interpretation": "single acceptance trace only",
            "repository_timing_interpretation": (
                "descriptive repeated path; later repetitions may reuse durable "
                "artifacts and provider caches"
            ),
        },
        "environment": environment,
        "run_manifest": manifest,
        "observed_outputs": {
            "qa_source_counts": sorted({int(row["source_count"]) for row in qa_rows}),
            "qa_source_match_statuses": sorted(
                {row["source_match_status"] for row in qa_rows}
            ),
            "graph_node_counts": sorted(
                {int(row["graph_nodes"]) for row in graph_rows}
            ),
            "graph_edge_counts": sorted(
                {int(row["graph_edges"]) for row in graph_rows}
            ),
            "graph_statuses": sorted({row["graph_status"] for row in graph_rows}),
            "selected_arxiv_ids": sorted(
                {row["selected_arxiv_id"] for row in rows if row["selected_arxiv_id"]}
            ),
        },
        "results": [asdict(summary) for summary in summaries],
    }
    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    (EVALUATION_DIR / "summary.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    with (EVALUATION_DIR / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=list(asdict(summaries[0])),
            lineterminator="\n",
        )
        writer.writeheader()
        for summary in summaries:
            writer.writerow(asdict(summary))


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


def plot_results(
    rows: list[dict[str, str]],
    summaries: list[StageSummary],
) -> None:
    lookup = {(item.track, item.scenario): item for item in summaries}
    figure, axes = plt.subplots(1, 2, figsize=(10.2, 4.8))

    repository = [lookup[("live_repository", stage)] for stage in REPOSITORY_SCENARIOS]
    labels = [display_label(item.scenario, rows) for item in repository]
    positions = list(range(len(repository)))
    colors = [TEAL if item.success_rate == 1.0 else CORAL for item in repository]
    axes[0].barh(
        positions,
        [item.success_rate * 100 for item in repository],
        color=colors,
    )
    axes[0].set_yticks(positions, labels)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, 105)
    axes[0].set_xlabel("Successful repetitions (%)")
    axes[0].set_title(
        "Repeated production-repository path", loc="left", fontweight="bold"
    )
    axes[0].grid(axis="x")
    for position, item in zip(positions, repository, strict=True):
        axes[0].text(
            item.success_rate * 100 + 1,
            position,
            f"{item.success_count}/{item.n}",
            va="center",
            color=INK,
        )

    ui_rows = [
        next(
            row
            for row in rows
            if row["track"] == "live_ui" and row["scenario"] == stage
        )
        for stage in UI_SCENARIOS
    ]
    ui_durations = [float(row["duration_ms"]) / 1000 for row in ui_rows]
    ui_colors = [BLUE if as_success(row["success"]) else CORAL for row in ui_rows]
    axes[1].barh(
        list(range(len(ui_rows))),
        ui_durations,
        color=ui_colors,
    )
    axes[1].set_yticks(
        list(range(len(ui_rows))),
        [display_label(row["scenario"], rows) for row in ui_rows],
    )
    axes[1].invert_yaxis()
    axes[1].set_xscale("log")
    axes[1].set_xlabel("Observed stage duration (s, log scale)")
    axes[1].set_title(
        "Single live Compose acceptance trace", loc="left", fontweight="bold"
    )
    axes[1].grid(axis="x")
    axes[1].text(
        0.01,
        -0.16,
        "Blue: criterion met; coral: criterion not met. Durations are descriptive.",
        transform=axes[1].transAxes,
        color=MUTED,
        fontsize=8,
    )

    figure.tight_layout()
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    for suffix in ("pdf", "png"):
        figure.savefig(
            FIGURE_DIR / f"live_core_acceptance.{suffix}",
            dpi=220,
            bbox_inches="tight",
        )
    plt.close(figure)


def main() -> None:
    rows = read_csv()
    environment = read_json("environment.json")
    manifest = read_json("run_manifest.json")
    validate_protocol(rows)
    summaries = summarize(rows)
    write_results(rows, summaries, environment, manifest)
    configure_plots()
    plot_results(rows, summaries)
    failed = [row for row in rows if not as_success(row["success"])]
    print(
        json.dumps(
            {
                "rows": len(rows),
                "failed_rows": len(failed),
                "summary_rows": len(summaries),
                "selected_arxiv_ids": sorted(
                    {
                        row["selected_arxiv_id"]
                        for row in rows
                        if row["selected_arxiv_id"]
                    }
                ),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
