"""Resilient arXiv PDF download behavior."""

import asyncio
import hashlib
from pathlib import Path

import httpx
import pytest

from mneme.services.documents import (
    PdfDownloader,
    PdfDownloadError,
    PdfDownloadResult,
    versioned_pdf_url,
)

PDF = b"%PDF-1.7\nfixture\n"


def _run(
    tmp_path: Path,
    handler,
    *,
    expected_checksum: str | None = None,
    max_bytes: int = 1024,
) -> tuple[PdfDownloadResult, list[float]]:
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    async def execute():
        async with PdfDownloader(
            user_agent="Mneme/Test",
            request_interval_seconds=0,
            timeout_seconds=1,
            max_attempts=3,
            max_bytes=max_bytes,
            transport=httpx.MockTransport(handler),
            sleep=sleep,
        ) as downloader:
            return await downloader.download(
                url=versioned_pdf_url("2607.00001", 2),
                destination=tmp_path / "source.pdf",
                expected_checksum=expected_checksum,
            )

    return asyncio.run(execute()), sleeps


@pytest.mark.base
@pytest.mark.pipeline
def test_existing_matching_pdf_is_reused_without_request(tmp_path: Path) -> None:
    destination = tmp_path / "source.pdf"
    destination.write_bytes(PDF)
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(500, request=request)

    result, _ = _run(tmp_path, handler, expected_checksum=hashlib.sha256(PDF).hexdigest())

    assert result.reused is True
    assert requests == 0


@pytest.mark.base
@pytest.mark.pipeline
def test_retryable_status_is_retried_and_retry_after_is_honored(tmp_path: Path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, headers={"Retry-After": "4"}, request=request)
        return httpx.Response(200, content=PDF, request=request)

    result, sleeps = _run(tmp_path, handler)

    assert result.path.exists()
    assert attempts == 2
    assert sleeps == [4.0]


@pytest.mark.base
@pytest.mark.pipeline
def test_transport_failure_is_retried(tmp_path: Path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, content=PDF, request=request)

    result, sleeps = _run(tmp_path, handler)

    assert result.path.exists()
    assert attempts == 2
    assert sleeps == [1]


@pytest.mark.base
@pytest.mark.pipeline
@pytest.mark.parametrize(
    ("response", "code"),
    [
        (httpx.Response(404), "pdf_download_rejected"),
        (httpx.Response(200, content=b"<html>error</html>"), "invalid_pdf"),
    ],
)
def test_terminal_responses_leave_no_artifact(
    tmp_path: Path, response: httpx.Response, code: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        response.request = request
        return response

    with pytest.raises(PdfDownloadError) as captured:
        _run(tmp_path, handler)

    assert captured.value.code == code
    assert not (tmp_path / "source.pdf").exists()
    assert list(tmp_path.glob(".*.tmp")) == []


@pytest.mark.base
@pytest.mark.pipeline
def test_stream_larger_than_limit_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PDF + b"x" * 100, request=request)

    with pytest.raises(PdfDownloadError) as captured:
        _run(tmp_path, handler, max_bytes=len(PDF))

    assert captured.value.code == "pdf_too_large"


@pytest.mark.base
@pytest.mark.pipeline
def test_declared_content_length_over_limit_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=PDF,
            headers={"Content-Length": "4096"},
            request=request,
        )

    with pytest.raises(PdfDownloadError) as captured:
        _run(tmp_path, handler, max_bytes=1024)

    assert captured.value.code == "pdf_too_large"


@pytest.mark.base
@pytest.mark.pipeline
def test_checksum_mismatch_preserves_existing_destination(tmp_path: Path) -> None:
    destination = tmp_path / "source.pdf"
    old = b"%PDF-1.7\nold\n"
    destination.write_bytes(old)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PDF, request=request)

    with pytest.raises(PdfDownloadError) as captured:
        _run(tmp_path, handler, expected_checksum="a" * 64)

    assert captured.value.code == "source_checksum_mismatch"
    assert destination.read_bytes() == old
