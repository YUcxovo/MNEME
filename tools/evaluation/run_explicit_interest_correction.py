#!/usr/bin/env python3
"""Evaluate explicit-interest correction with the production recommendation scorer."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import fmean
from typing import Any
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = ROOT / "backend" / "src"
sys.path.insert(0, str(BACKEND_SRC))

from mneme.ai.recommendation import PaperCandidate, PreferenceView, rank_candidates  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fixture",
        type=Path,
        default=ROOT / "tools/evaluation/fixtures/explicit_interest_correction.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "docs/evaluation/explicit-interest-correction",
    )
    return parser.parse_args()


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_by_topic(rows: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["candidate_topic"]].append(row)
    return {
        topic: {
            "mean_score": round(fmean(item["score"] for item in items), 6),
            "mean_rank": round(fmean(item["rank"] for item in items), 3),
            "topic_reason_rate": round(
                fmean(1.0 if item["topic_reason_present"] else 0.0 for item in items),
                3,
            ),
        }
        for topic, items in sorted(grouped.items())
    }


def transition(
    summaries: dict[str, dict[str, dict[str, float]]],
    *,
    transition_id: str,
    before: str,
    after: str,
    topic: str,
    expected_direction: str,
) -> dict[str, Any]:
    before_value = summaries[before][topic]
    after_value = summaries[after][topic]
    score_delta = round(after_value["mean_score"] - before_value["mean_score"], 6)
    rank_delta = round(after_value["mean_rank"] - before_value["mean_rank"], 3)
    reason_delta = round(
        after_value["topic_reason_rate"] - before_value["topic_reason_rate"],
        3,
    )
    direction_passed = score_delta > 0 if expected_direction == "increase" else score_delta < 0
    return {
        "transition_id": transition_id,
        "before_state": before,
        "after_state": after,
        "candidate_topic": topic,
        "expected_score_direction": expected_direction,
        "mean_score_before": before_value["mean_score"],
        "mean_score_after": after_value["mean_score"],
        "score_delta": score_delta,
        "mean_rank_before": before_value["mean_rank"],
        "mean_rank_after": after_value["mean_rank"],
        "rank_delta": rank_delta,
        "topic_reason_rate_before": before_value["topic_reason_rate"],
        "topic_reason_rate_after": after_value["topic_reason_rate"],
        "reason_rate_delta": reason_delta,
        "passed": direction_passed,
    }


def main() -> int:
    args = parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    output = args.output
    raw_dir = output / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    reference_time = datetime.fromisoformat(fixture["reference_time"])
    published_at = reference_time - timedelta(days=fixture["candidate_age_days"])
    candidates = [
        PaperCandidate(
            paper_id=UUID(item["paper_id"]),
            title=item["title"],
            categories=tuple(item["categories"]),
            published_at=published_at,
        )
        for item in fixture["candidates"]
    ]
    metadata_by_id = {item["paper_id"]: item for item in fixture["candidates"]}

    rows: list[dict[str, Any]] = []
    state_topics: dict[str, list[str]] = {}
    for state in fixture["states"]:
        state_id = state["state_id"]
        topics = list(state["topics"])
        state_topics[state_id] = topics
        ranked = rank_candidates(
            candidates,
            PreferenceView(explicit_topics=tuple(topics)),
            now=reference_time,
            limit=len(candidates),
        )
        for rank, scored in enumerate(ranked, start=1):
            paper_id = str(scored.paper_id)
            candidate = metadata_by_id[paper_id]
            expected_reason = f"Matches your topics: {candidate['topic']}"
            rows.append(
                {
                    "state_id": state_id,
                    "active_topics": "|".join(topics),
                    "paper_id": paper_id,
                    "candidate_topic": candidate["topic"],
                    "title": candidate["title"],
                    "rank": rank,
                    "score": scored.score,
                    "reasons": " | ".join(scored.reasons),
                    "topic_reason_present": expected_reason in scored.reasons,
                }
            )

    state_summaries = {
        state_id: mean_by_topic([row for row in rows if row["state_id"] == state_id])
        for state_id in state_topics
    }
    transitions = [
        transition(
            state_summaries,
            transition_id="add_quantum",
            before="attention_only",
            after="add_quantum",
            topic="quantum",
            expected_direction="increase",
        ),
        transition(
            state_summaries,
            transition_id="edit_remove_quantum",
            before="add_quantum",
            after="edit_quantum_to_robotics",
            topic="quantum",
            expected_direction="decrease",
        ),
        transition(
            state_summaries,
            transition_id="edit_add_robotics",
            before="add_quantum",
            after="edit_quantum_to_robotics",
            topic="robotics",
            expected_direction="increase",
        ),
        transition(
            state_summaries,
            transition_id="delete_robotics",
            before="edit_quantum_to_robotics",
            after="delete_robotics",
            topic="robotics",
            expected_direction="decrease",
        ),
    ]

    raw_path = raw_dir / "candidate_results.csv"
    with raw_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary_path = output / "summary.csv"
    with summary_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(transitions[0]))
        writer.writeheader()
        writer.writerows(transitions)

    result = {
        "fixture_id": fixture["fixture_id"],
        "production_function": "mneme.ai.recommendation.rank_candidates",
        "candidate_count": len(candidates),
        "state_count": len(state_topics),
        "transition_count": len(transitions),
        "passed_transitions": sum(1 for item in transitions if item["passed"]),
        "all_transitions_passed": all(item["passed"] for item in transitions),
        "state_topics": state_topics,
        "state_summaries": state_summaries,
        "transitions": transitions,
    }
    (output / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "fixture_sha256": file_sha256(args.fixture),
        "scorer_sha256": file_sha256(BACKEND_SRC / "mneme/ai/recommendation.py"),
        "runner_sha256": file_sha256(Path(__file__)),
        "command": "python tools/evaluation/run_explicit_interest_correction.py",
    }
    (raw_dir / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["all_transitions_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
