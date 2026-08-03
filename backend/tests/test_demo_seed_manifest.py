"""Tests for strict reproducible demo seed inputs."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mneme.demo.manifest import (
    DemoManifestError,
    DemoSeedManifest,
    load_default_demo_seed_manifest,
    load_demo_seed_manifest,
)
from mneme.models.user import UserEventType

ANCHOR = datetime(2026, 8, 3, 12, tzinfo=UTC)


def _payload() -> dict[str, object]:
    return load_default_demo_seed_manifest().model_dump(mode="json")


@pytest.mark.base
def test_default_manifest_matches_live_core_without_generated_artifacts() -> None:
    manifest = load_default_demo_seed_manifest()
    serialized = json.dumps(manifest.model_dump(mode="json"), sort_keys=True)

    assert manifest.schema_version == "demo-seed-manifest-v1"
    assert manifest.manifest_id == "mneme-live-core-v1"
    assert manifest.seed_arxiv_reference == "1706.03762"
    assert manifest.onboarding_limit == 5
    assert len(manifest.events) == 8
    assert len(manifest.content_sha256()) == 64
    assert all(term not in serialized for term in ("summary", "answer", "embedding", "graph_edge"))


@pytest.mark.base
def test_manifest_normalizes_preferences_and_arxiv_version() -> None:
    payload = _payload()
    payload["seed_arxiv_reference"] = "https://arxiv.org/abs/1706.03762v7"
    payload["topics"] = [" Machine Learning ", "machine learning", "AI"]

    manifest = DemoSeedManifest.model_validate(payload)

    assert manifest.seed_arxiv_reference == "1706.03762"
    assert manifest.topics == ["machine learning", "ai"]


@pytest.mark.base
def test_manifest_generates_stable_event_ids_and_relative_times() -> None:
    manifest = load_default_demo_seed_manifest()
    event = manifest.events[0]

    assert manifest.event_id(event) == manifest.event_id(event)
    assert manifest.event_time(event, ANCHOR) == ANCHOR - timedelta(
        seconds=event.seconds_before_anchor
    )
    with pytest.raises(DemoManifestError):
        manifest.event_time(event, datetime(2026, 8, 3))


@pytest.mark.base
@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update({"unknown": True}),
        lambda payload: payload.update({"schema_version": "future"}),
        lambda payload: payload.update({"onboarding_limit": 4}),
        lambda payload: payload["events"].append(payload["events"][0]),
        lambda payload: payload["events"][4].update({"paper_rank": 5}),
        lambda payload: payload["events"][4].update({"duration_ms": 20}),
        lambda payload: payload.update(
            {
                "events": [
                    event for event in payload["events"] if event["event_type"] != "paper_skipped"
                ]
            }
        ),
        lambda payload: payload.update(
            {
                "events": [
                    event
                    for event in payload["events"]
                    if event["event_type"] not in {"paper_saved", "question_asked"}
                ]
            }
        ),
    ],
)
def test_manifest_rejects_invalid_or_unbalanced_inputs(mutate: object) -> None:
    payload = _payload()
    assert callable(mutate)
    mutate(payload)

    with pytest.raises(ValueError):
        DemoSeedManifest.model_validate(payload)


@pytest.mark.base
def test_skip_requires_a_preceding_impression() -> None:
    payload = _payload()
    events = payload["events"]
    assert isinstance(events, list)
    events[:] = [
        event
        for event in events
        if not (event["paper_rank"] == 2 and event["event_type"] == UserEventType.PAPER_IMPRESSION)
    ]

    with pytest.raises(ValueError):
        DemoSeedManifest.model_validate(payload)


@pytest.mark.base
def test_manifest_loader_rejects_symlink_and_invalid_json(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not-json", encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(invalid)

    with pytest.raises(DemoManifestError):
        load_demo_seed_manifest(invalid)
    with pytest.raises(DemoManifestError):
        load_demo_seed_manifest(linked)
