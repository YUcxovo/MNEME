"""Rate-limited, retrying downloads of versioned arXiv PDFs."""

import asyncio
import hashlib
import os
import tempfile
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Self

import httpx

from mneme.services.documents.pdf_transport import (
    RETRYABLE_STATUS_CODES,
    PdfDownloadError,
    PdfDownloadResult,
    parse_retry_after,
    validate_pdf_url,
)

_PDF_MAGIC = b"%PDF-"
_MAGIC_SCAN_BYTES = 1024


class PdfDownloader:
    """Stream PDFs to disk while honoring arXiv request etiquette."""

    def __init__(
        self,
        *,
        user_agent: str,
        request_interval_seconds: float,
        timeout_seconds: float,
        max_attempts: int,
        max_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._request_interval_seconds = request_interval_seconds
        self._max_attempts = max_attempts
        self._max_bytes = max_bytes
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request_started: float | None = None
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=timeout_seconds,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            headers={"User-Agent": user_agent},
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def download(
        self,
        *,
        url: str,
        destination: Path,
        expected_checksum: str | None = None,
    ) -> PdfDownloadResult:
        """Install one validated PDF without exposing partial artifacts."""
        validate_pdf_url(url)
        existing = self._existing(destination, expected_checksum)
        if existing is not None:
            return existing

        last_error: PdfDownloadError | None = None
        for attempt in range(self._max_attempts):
            try:
                return await self._download_once(
                    url=url,
                    destination=destination,
                    expected_checksum=expected_checksum,
                )
            except PdfDownloadError as error:
                last_error = error
                if not error.retryable or attempt + 1 == self._max_attempts:
                    raise
                await self._sleep(max(float(2**attempt), error.retry_after or 0.0))
            except httpx.TransportError as error:
                last_error = PdfDownloadError(
                    "pdf_download_failed",
                    "The arXiv PDF download failed after retries.",
                    retryable=True,
                )
                if attempt + 1 == self._max_attempts:
                    raise last_error from error
                await self._sleep(2**attempt)
        if last_error is not None:
            raise last_error
        raise AssertionError("unreachable PDF retry loop")

    async def _download_once(
        self, *, url: str, destination: Path, expected_checksum: str | None
    ) -> PdfDownloadResult:
        response = await self._request(url)
        try:
            if response.status_code in RETRYABLE_STATUS_CODES:
                delay = parse_retry_after(response, now=self._wall_clock())
                raise PdfDownloadError(
                    "pdf_upstream_unavailable",
                    f"arXiv PDF request failed with HTTP {response.status_code}.",
                    retryable=True,
                    retry_after=delay,
                )
            if response.status_code != 200:
                raise PdfDownloadError(
                    "pdf_download_rejected",
                    f"arXiv PDF request failed with HTTP {response.status_code}.",
                )
            validate_pdf_url(str(response.url))
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = 0
                if declared_size > self._max_bytes:
                    raise PdfDownloadError("pdf_too_large", "The PDF exceeds the configured limit.")
            return await self._stream_to_file(response, destination, expected_checksum)
        finally:
            await response.aclose()

    async def _request(self, url: str) -> httpx.Response:
        async with self._lock:
            if self._last_request_started is not None:
                delay = self._last_request_started + self._request_interval_seconds - self._clock()
                if delay > 0:
                    await self._sleep(delay)
            self._last_request_started = self._clock()
            request = self._client.build_request("GET", url)
            return await self._client.send(request, stream=True)

    async def _stream_to_file(
        self, response: httpx.Response, destination: Path, expected_checksum: str | None
    ) -> PdfDownloadResult:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=destination.parent, prefix=f".{destination.name}.", suffix=".tmp"
        )
        temporary = Path(temporary_name)
        digest = hashlib.sha256()
        prefix = bytearray()
        byte_size = 0
        try:
            with os.fdopen(descriptor, "wb") as stream:
                async for chunk in response.aiter_bytes():
                    byte_size += len(chunk)
                    if byte_size > self._max_bytes:
                        raise PdfDownloadError(
                            "pdf_too_large", "The PDF exceeds the configured limit."
                        )
                    digest.update(chunk)
                    if len(prefix) < _MAGIC_SCAN_BYTES:
                        prefix.extend(chunk[: _MAGIC_SCAN_BYTES - len(prefix)])
                    stream.write(chunk)
                stream.flush()
                os.fsync(stream.fileno())
            if _PDF_MAGIC not in prefix:
                raise PdfDownloadError("invalid_pdf", "The downloaded file is not a PDF.")
            checksum = digest.hexdigest()
            if expected_checksum is not None and checksum != expected_checksum:
                raise PdfDownloadError(
                    "source_checksum_mismatch",
                    "The arXiv revision no longer matches its stored checksum.",
                )
            os.replace(temporary, destination)
            return PdfDownloadResult(destination, checksum, byte_size, reused=False)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise

    def _existing(
        self, destination: Path, expected_checksum: str | None
    ) -> PdfDownloadResult | None:
        if not destination.is_file():
            return None
        byte_size = destination.stat().st_size
        if byte_size > self._max_bytes:
            return None
        digest = hashlib.sha256()
        with destination.open("rb") as stream:
            prefix = stream.read(_MAGIC_SCAN_BYTES)
            digest.update(prefix)
            for chunk in iter(lambda: stream.read(64 * 1024), b""):
                digest.update(chunk)
        if _PDF_MAGIC not in prefix:
            return None
        checksum = digest.hexdigest()
        if expected_checksum is not None and checksum != expected_checksum:
            return None
        return PdfDownloadResult(destination, checksum, byte_size, reused=True)
