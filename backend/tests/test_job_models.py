"""Metadata tests for persisted pipeline job state."""

import pytest
from sqlalchemy import Enum

from mneme.models import Base, JobStatus, PipelineStage


@pytest.mark.base
@pytest.mark.db
def test_pipeline_job_contract() -> None:
    table = Base.metadata.tables["pipeline_jobs"]
    stage_type = table.c.stage.type
    status_type = table.c.status.type

    assert table.c.paper_id.nullable
    assert table.c.paper_version_id.nullable
    assert table.c.idempotency_key.unique
    assert table.c.error_code.nullable
    assert isinstance(stage_type, Enum)
    assert set(stage_type.enums) == {stage.value for stage in PipelineStage}
    assert isinstance(status_type, Enum)
    assert set(status_type.enums) == {status.value for status in JobStatus}


@pytest.mark.base
@pytest.mark.db
def test_pipeline_job_indexes_and_checks() -> None:
    table = Base.metadata.tables["pipeline_jobs"]
    names = {constraint.name for constraint in table.constraints}

    assert "ck_pipeline_jobs_attempts_non_negative" in names
    assert "ck_pipeline_jobs_version_requires_paper" in names
    assert "fk_pipeline_jobs_version_paper" in names
    assert "ck_pipeline_jobs_time_range_valid" in names
    assert {
        "ix_pipeline_jobs_status_stage",
        "ix_pipeline_jobs_paper_status",
        "ix_pipeline_jobs_version_status",
    } <= {index.name for index in table.indexes}
