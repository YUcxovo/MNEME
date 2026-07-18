"""Frozen v0.1 async job response schema."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from mneme.models.job import JobStatus, PipelineJob


class Job(BaseModel):
    """Public state of one asynchronous pipeline job."""

    id: UUID
    stage: str
    status: JobStatus
    error_code: str | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_model(cls, job: PipelineJob) -> Job:
        """Map a durable pipeline job to the public contract."""
        return cls(
            id=job.id,
            stage=job.stage.value,
            status=job.status,
            error_code=job.error_code,
            updated_at=job.updated_at,
        )
