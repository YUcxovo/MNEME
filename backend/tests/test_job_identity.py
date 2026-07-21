"""Pure tests for canonical durable pipeline-job identities."""

import re
from uuid import UUID

import pytest

from mneme.models.job import PipelineStage
from mneme.repositories.job_identity import build_job_idempotency_key, summarize_idempotency_key

PAPER_ID = UUID("00000000-0000-0000-0000-000000000111")
VERSION_ID = UUID("00000000-0000-0000-0000-000000000222")

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


def test_job_key_is_canonical_and_hides_raw_scope_values() -> None:
    first = build_job_idempotency_key(
        stage=PipelineStage.PARSE_PDF,
        scope={"paper_id": PAPER_ID, "paper_version_id": VERSION_ID},
        inputs={"parser": "parser-v1", "checksums": ["b" * 64, "a" * 64]},
    )
    reordered = build_job_idempotency_key(
        stage=PipelineStage.PARSE_PDF,
        scope={"paper_version_id": VERSION_ID, "paper_id": PAPER_ID},
        inputs={"checksums": ("b" * 64, "a" * 64), "parser": "parser-v1"},
    )

    assert first == reordered
    assert re.fullmatch(r"v1:parse_pdf:[0-9a-f]{64}", first)
    assert str(PAPER_ID) not in first
    assert "parser-v1" not in first


def test_content_inputs_and_revision_change_the_job_identity() -> None:
    original = build_job_idempotency_key(
        stage=PipelineStage.PARSE_PDF,
        scope={"paper_id": PAPER_ID, "paper_version_id": VERSION_ID},
        inputs={"source_checksum": "a" * 64},
    )
    changed_input = build_job_idempotency_key(
        stage=PipelineStage.PARSE_PDF,
        scope={"paper_id": PAPER_ID, "paper_version_id": VERSION_ID},
        inputs={"source_checksum": "b" * 64},
    )
    changed_revision = build_job_idempotency_key(
        stage=PipelineStage.PARSE_PDF,
        scope={"paper_id": PAPER_ID, "paper_version_id": UUID(int=3)},
        inputs={"source_checksum": "a" * 64},
    )

    assert len({original, changed_input, changed_revision}) == 3


def test_pipeline_version_is_part_of_the_job_identity() -> None:
    v1 = build_job_idempotency_key(
        stage=PipelineStage.FETCH_METADATA,
        scope={"category": "cs.AI", "date": "2026-07-21"},
        inputs={},
    )
    v2 = build_job_idempotency_key(
        stage=PipelineStage.FETCH_METADATA,
        scope={"category": "cs.AI", "date": "2026-07-21"},
        inputs={},
        pipeline_version="v2",
    )

    assert v1.startswith("v1:fetch_metadata:")
    assert v2.startswith("v2:fetch_metadata:")
    assert v1 != v2


def test_summary_key_is_scoped_to_one_exact_revision() -> None:
    first = summarize_idempotency_key(paper_id=PAPER_ID, paper_version_id=VERSION_ID)
    next_revision = summarize_idempotency_key(paper_id=PAPER_ID, paper_version_id=UUID(int=3))

    assert first != next_revision


@pytest.mark.parametrize(
    ("scope", "inputs", "pipeline_version", "exception"),
    [
        ({}, {}, "v1", ValueError),
        ({"paper": PAPER_ID}, {"weight": 0.5}, "v1", TypeError),
        ({"paper": PAPER_ID}, {}, "version with spaces", ValueError),
    ],
)
def test_invalid_identity_components_are_rejected(
    scope: dict[str, object],
    inputs: dict[str, object],
    pipeline_version: str,
    exception: type[Exception],
) -> None:
    with pytest.raises(exception):
        build_job_idempotency_key(
            stage=PipelineStage.SUMMARIZE_PAPER,
            scope=scope,
            inputs=inputs,
            pipeline_version=pipeline_version,
        )
