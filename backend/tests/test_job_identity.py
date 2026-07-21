"""Pure tests for canonical durable pipeline-job identities."""

import re
from datetime import date
from uuid import UUID

import pytest

from mneme.models.job import PipelineStage
from mneme.repositories.job_identity import (
    build_job_idempotency_key,
    chunk_idempotency_key,
    download_idempotency_key,
    embed_idempotency_key,
    parse_idempotency_key,
    summarize_idempotency_key,
    weekly_digest_idempotency_key,
)

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
    first = summarize_idempotency_key(
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        parsed_checksum="a" * 64,
        parser_version="parser-v1",
    )
    next_revision = summarize_idempotency_key(
        paper_id=PAPER_ID,
        paper_version_id=UUID(int=3),
        parsed_checksum="a" * 64,
        parser_version="parser-v1",
    )

    assert first != next_revision


def test_named_revision_stage_keys_include_their_artifact_inputs() -> None:
    download = download_idempotency_key(
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        arxiv_id="2607.00001",
        version_number=2,
    )
    parse = parse_idempotency_key(
        paper_id=PAPER_ID, paper_version_id=VERSION_ID, source_checksum="a" * 64
    )
    summary = summarize_idempotency_key(
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        parsed_checksum="b" * 64,
        parser_version="parser-v1",
    )
    chunk = chunk_idempotency_key(
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        parsed_checksum="b" * 64,
        parser_version="parser-v1",
    )
    embed = embed_idempotency_key(
        paper_id=PAPER_ID,
        paper_version_id=VERSION_ID,
        parsed_checksum="b" * 64,
        parser_version="parser-v1",
        embedding_model="embedding-v1",
    )

    assert download.startswith("v1:download_pdf:")
    assert parse.startswith("v1:parse_pdf:")
    assert summary.startswith("v1:summarize_paper:")
    assert chunk.startswith("v1:chunk_paper:")
    assert embed.startswith("v1:embed_chunks:")
    assert len({download, parse, summary, chunk, embed}) == 5


def test_weekly_digest_key_is_scoped_by_user_period_and_generator() -> None:
    monday = date(2026, 7, 20)
    original = weekly_digest_idempotency_key(
        user_id=PAPER_ID,
        week_start=monday,
        generator_version="recommender-v1",
    )

    assert original.startswith("v1:assemble_digest:")
    assert original == weekly_digest_idempotency_key(
        user_id=PAPER_ID,
        week_start=monday,
        generator_version="recommender-v1",
    )
    assert original != weekly_digest_idempotency_key(
        user_id=VERSION_ID,
        week_start=monday,
        generator_version="recommender-v1",
    )
    with pytest.raises(ValueError, match="Monday"):
        weekly_digest_idempotency_key(
            user_id=PAPER_ID,
            week_start=date(2026, 7, 21),
            generator_version="recommender-v1",
        )


@pytest.mark.parametrize("checksum", ["", "A" * 64, "a" * 63, "not-a-checksum"])
def test_named_artifact_keys_reject_invalid_checksums(checksum: str) -> None:
    with pytest.raises(ValueError):
        parse_idempotency_key(
            paper_id=PAPER_ID,
            paper_version_id=VERSION_ID,
            source_checksum=checksum,
        )


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
