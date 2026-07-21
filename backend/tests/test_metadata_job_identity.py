"""Durable identity rules for daily metadata collection jobs."""

from datetime import date
from uuid import UUID

import pytest

from mneme.models.job import JobStatus, PipelineJob, PipelineStage
from mneme.tasks import metadata_jobs

RUN_DATE = date(2026, 7, 21)

pytestmark = [pytest.mark.base, pytest.mark.pipeline]


def _job(*, category: str = "cs.AI") -> PipelineJob:
    return PipelineJob(
        id=UUID("00000000-0000-0000-0000-000000000333"),
        idempotency_key=metadata_jobs.metadata_idempotency_key(
            category=category, run_date=RUN_DATE
        ),
        stage=PipelineStage.FETCH_METADATA,
        paper_id=None,
        paper_version_id=None,
        pipeline_version="v1",
        status=JobStatus.QUEUED,
        attempt_count=0,
    )


def test_category_and_date_define_metadata_job_identity() -> None:
    original = metadata_jobs.metadata_idempotency_key(category="cs.AI", run_date=RUN_DATE)

    assert original == metadata_jobs.metadata_idempotency_key(category="cs.AI", run_date=RUN_DATE)
    assert original != metadata_jobs.metadata_idempotency_key(category="cs.LG", run_date=RUN_DATE)
    assert original != metadata_jobs.metadata_idempotency_key(
        category="cs.AI", run_date=date(2026, 7, 22)
    )


def test_parent_identity_requires_the_exact_collection_scope() -> None:
    expected = metadata_jobs.metadata_idempotency_key(category="cs.AI", run_date=RUN_DATE)

    assert metadata_jobs._valid_parent(_job(), expected_key=expected)
    assert not metadata_jobs._valid_parent(_job(category="cs.LG"), expected_key=expected)

    revision_scoped = _job()
    revision_scoped.paper_id = UUID("00000000-0000-0000-0000-000000000111")
    assert not metadata_jobs._valid_parent(revision_scoped, expected_key=expected)
