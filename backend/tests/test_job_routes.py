"""Contract tests for GET /jobs/{job_id}."""

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response

from mneme.api.dependencies.ai import get_pipeline_job_repository
from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.errors import register_error_handlers
from mneme.api.middleware import request_context_middleware
from mneme.api.routes.jobs import router as jobs_router
from mneme.models.job import JobStatus, PipelineJob, PipelineStage

USER_ID = UUID("00000000-0000-0000-0000-000000000111")
JOB_ID = UUID("00000000-0000-0000-0000-000000000222")
UPDATED_AT = datetime(2026, 7, 21, 8, 30, tzinfo=UTC)


class FakeJobRepository:
    """Single-job repository fake."""

    def __init__(self, job: PipelineJob | None) -> None:
        self.job = job

    async def get(self, job_id: UUID) -> PipelineJob | None:
        if self.job is not None and self.job.id == job_id:
            return self.job
        return None


def _job() -> PipelineJob:
    return PipelineJob(
        id=JOB_ID,
        paper_id=uuid4(),
        idempotency_key=f"v1:summarize_paper:{JOB_ID}",
        stage=PipelineStage.SUMMARIZE_PAPER,
        status=JobStatus.FAILED,
        error_code="ai_provider_error",
        last_error="secret provider diagnostics",
        pipeline_version="v1",
        updated_at=UPDATED_AT,
    )


def _application(repository: FakeJobRepository) -> FastAPI:
    async def principal_override() -> Principal:
        return Principal(user_id=USER_ID)

    application = FastAPI()
    application.middleware("http")(request_context_middleware)
    register_error_handlers(application)
    application.include_router(jobs_router, prefix="/v1")
    application.dependency_overrides[require_principal] = principal_override
    application.dependency_overrides[get_pipeline_job_repository] = lambda: repository
    return application


async def _get(application: FastAPI, path: str) -> Response:
    transport = ASGITransport(app=application)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


@pytest.mark.base
@pytest.mark.api
def test_job_status_matches_frozen_contract_without_internal_error() -> None:
    response = asyncio.run(_get(_application(FakeJobRepository(_job())), f"/v1/jobs/{JOB_ID}"))

    assert response.status_code == 200
    assert response.json() == {
        "id": str(JOB_ID),
        "stage": "summarize_paper",
        "status": "failed",
        "error_code": "ai_provider_error",
        "updated_at": UPDATED_AT.isoformat().replace("+00:00", "Z"),
    }
    assert "secret provider diagnostics" not in response.text


@pytest.mark.base
@pytest.mark.api
def test_unknown_job_returns_stable_not_found_error() -> None:
    response = asyncio.run(_get(_application(FakeJobRepository(None)), f"/v1/jobs/{uuid4()}"))

    assert response.status_code == 404
    assert response.json()["code"] == "job_not_found"


@pytest.mark.base
@pytest.mark.api
def test_invalid_job_id_uses_shared_validation_error() -> None:
    response = asyncio.run(_get(_application(FakeJobRepository(None)), "/v1/jobs/not-a-uuid"))

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


@pytest.mark.base
@pytest.mark.api
def test_job_route_uses_frozen_operation_id() -> None:
    application = _application(FakeJobRepository(None))

    operation = application.openapi()["paths"]["/v1/jobs/{job_id}"]["get"]

    assert operation["operationId"] == "getJob"
