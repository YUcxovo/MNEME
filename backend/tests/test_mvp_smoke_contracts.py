"""Safety and HTTP-boundary tests for the MVP smoke runner."""

import asyncio
import json
from pathlib import Path
from uuid import UUID

import httpx
import pytest

from mneme.api.schemas.jobs import Job
from mneme.demo.smoke_client import MvpSmokeClient
from mneme.demo.smoke_types import (
    MvpSmokeConfig,
    MvpSmokeConfigurationError,
    MvpSmokeError,
    MvpSmokeReport,
    SmokeCheck,
    read_private_smoke_token,
    validate_smoke_token,
)


@pytest.mark.base
def test_smoke_config_allows_https_and_loopback_http() -> None:
    assert MvpSmokeConfig(base_url="https://demo.mneme.example").base_url.startswith("https")
    assert MvpSmokeConfig(base_url="http://127.0.0.1:8000").base_url.startswith("http")
    assert MvpSmokeConfig(base_url="http://[::1]:8000").base_url.startswith("http")


@pytest.mark.base
@pytest.mark.parametrize(
    "url",
    [
        "http://demo.mneme.example",
        "https://user:password@demo.mneme.example",
        "https://demo.mneme.example/v1",
        "https://demo.mneme.example?token=secret",
        "ftp://demo.mneme.example",
    ],
)
def test_smoke_config_rejects_unsafe_base_urls(url: str) -> None:
    with pytest.raises(MvpSmokeConfigurationError):
        MvpSmokeConfig(base_url=url)


@pytest.mark.base
def test_smoke_config_rejects_unbounded_inputs() -> None:
    with pytest.raises(MvpSmokeConfigurationError):
        MvpSmokeConfig(base_url="https://demo.example", deadline_seconds=3600)
    with pytest.raises(MvpSmokeConfigurationError):
        MvpSmokeConfig(base_url="https://demo.example", maximum_catalog_pages=0)
    with pytest.raises(MvpSmokeConfigurationError):
        MvpSmokeConfig(base_url="https://demo.example", question=" ")


@pytest.mark.base
def test_private_smoke_token_requires_owner_only_file(tmp_path: Path) -> None:
    token_file = tmp_path / "demo.token"
    token_file.write_text("opaque-token\n", encoding="ascii")
    token_file.chmod(0o600)

    assert read_private_smoke_token(token_file) == "opaque-token"

    token_file.chmod(0o644)
    with pytest.raises(MvpSmokeConfigurationError):
        read_private_smoke_token(token_file)


@pytest.mark.base
@pytest.mark.parametrize("token", ["", "with space", "line\nbreak", "x" * 4097])
def test_smoke_token_rejects_unsafe_values(token: str) -> None:
    with pytest.raises(MvpSmokeConfigurationError):
        validate_smoke_token(token)


@pytest.mark.base
def test_smoke_report_and_error_are_stable_and_sanitized() -> None:
    error = MvpSmokeError(
        "preferences", "unexpected_http_status", operation="preferences", status_code=401
    )
    report = MvpSmokeReport(
        seed_arxiv_id="1706.03762",
        checks=(SmokeCheck("preferences", "failed", error.safe_details()),),
    )

    assert report.as_dict() == {
        "checks": [
            {
                "details": {
                    "code": "unexpected_http_status",
                    "operation": "preferences",
                    "status_code": 401,
                },
                "name": "preferences",
                "status": "failed",
            }
        ],
        "schema_version": "mvp-smoke-report-v1",
        "seed_arxiv_id": "1706.03762",
        "status": "failed",
    }


@pytest.mark.base
def test_smoke_client_accepts_async_job_without_exposing_token() -> None:
    paper_id = UUID("00000000-0000-4000-8000-000000000001")
    job_id = UUID("00000000-0000-4000-8000-000000000002")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer raw-secret-token"
        if request.url.path.endswith("/summary"):
            return httpx.Response(
                202,
                json={
                    "id": str(job_id),
                    "stage": "summarize_paper",
                    "status": "queued",
                    "error_code": None,
                    "updated_at": "2026-08-03T00:00:00Z",
                },
            )
        return httpx.Response(401, json={"detail": "raw-secret-token"})

    http = httpx.AsyncClient(
        base_url="https://demo.example", transport=httpx.MockTransport(handler)
    )
    client = MvpSmokeClient(
        base_url="https://demo.example",
        token="raw-secret-token",
        timeout_seconds=30,
        client=http,
    )

    result = asyncio.run(client.summary(paper_id))
    assert isinstance(result, Job)
    assert result.id == job_id
    with pytest.raises(MvpSmokeError) as captured:
        asyncio.run(client.preferences())
    assert captured.value.safe_details()["status_code"] == 401
    assert "raw-secret-token" not in str(captured.value)
    assert "raw-secret-token" not in json.dumps(captured.value.__dict__)
    asyncio.run(client.aclose())


@pytest.mark.base
def test_smoke_client_sanitizes_invalid_response_content() -> None:
    http = httpx.AsyncClient(
        base_url="https://demo.example",
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json={"status": "secret-invalid-state"})
        ),
    )
    client = MvpSmokeClient(
        base_url="https://demo.example", token="token", timeout_seconds=30, client=http
    )

    with pytest.raises(MvpSmokeError) as captured:
        asyncio.run(client.readiness())

    assert captured.value.code == "invalid_response_schema"
    assert "secret-invalid-state" not in str(captured.value)
    assert "secret-invalid-state" not in json.dumps(captured.value.__dict__)
    asyncio.run(client.aclose())
