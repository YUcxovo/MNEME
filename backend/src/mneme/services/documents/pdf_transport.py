"""Shared values and validation for arXiv PDF transport."""

from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

import httpx

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
ALLOWED_PDF_HOSTS = {"arxiv.org", "export.arxiv.org"}


class PdfDownloadError(RuntimeError):
    """Safe failure raised by the PDF transport boundary."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        retry_after: float | None = None,
    ) -> None:
        self.code = code
        self.retryable = retryable
        self.retry_after = retry_after
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class PdfDownloadResult:
    """Metadata for one installed or reused PDF artifact."""

    path: Path
    checksum: str
    byte_size: int
    reused: bool


def versioned_pdf_url(arxiv_id: str, version_number: int) -> str:
    """Build the immutable PDF URL for one observed arXiv revision."""
    if not arxiv_id or version_number < 1:
        raise ValueError("A valid arXiv ID and positive version are required")
    return f"https://arxiv.org/pdf/{arxiv_id}v{version_number}"


def validate_pdf_url(url: str) -> None:
    """Reject non-arXiv destinations before opening a connection."""
    parsed = httpx.URL(url)
    if (
        parsed.scheme != "https"
        or parsed.host not in ALLOWED_PDF_HOSTS
        or not parsed.path.startswith("/pdf/")
    ):
        raise PdfDownloadError("invalid_pdf_url", "The PDF URL is not an arXiv PDF URL.")


def parse_retry_after(response: httpx.Response, *, now: datetime) -> float | None:
    """Parse either form of the HTTP Retry-After header."""
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
        except (TypeError, ValueError, OverflowError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=UTC)
        return max(0.0, (retry_at - now).total_seconds())
