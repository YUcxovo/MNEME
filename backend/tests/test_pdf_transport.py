"""Validation helpers for arXiv PDF transport."""

from datetime import UTC, datetime

import httpx
import pytest

from mneme.services.documents.pdf_transport import (
    PdfDownloadError,
    parse_retry_after,
    validate_pdf_url,
    versioned_pdf_url,
)


@pytest.mark.base
@pytest.mark.pipeline
def test_versioned_url_supports_modern_and_legacy_ids() -> None:
    assert versioned_pdf_url("2607.00001", 2) == "https://arxiv.org/pdf/2607.00001v2"
    assert versioned_pdf_url("hep-ex/0307015", 1).endswith("/hep-ex/0307015v1")


@pytest.mark.base
@pytest.mark.pipeline
def test_non_arxiv_pdf_url_is_rejected() -> None:
    with pytest.raises(PdfDownloadError, match="not an arXiv"):
        validate_pdf_url("https://example.com/pdf/paper")


@pytest.mark.base
@pytest.mark.pipeline
def test_retry_after_supports_seconds_and_http_date() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    seconds = httpx.Response(503, headers={"Retry-After": "4"})
    date = httpx.Response(503, headers={"Retry-After": "Tue, 21 Jul 2026 12:00:09 GMT"})

    assert parse_retry_after(seconds, now=now) == 4
    assert parse_retry_after(date, now=now) == 9
