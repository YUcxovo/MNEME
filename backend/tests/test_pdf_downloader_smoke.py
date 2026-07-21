"""Happy-path smoke test for the arXiv PDF downloader."""

import asyncio
from pathlib import Path

import httpx
import pytest

from mneme.services.documents import PdfDownloader, versioned_pdf_url


@pytest.mark.base
@pytest.mark.pipeline
def test_pdf_download_is_installed_atomically(tmp_path: Path) -> None:
    content = b"%PDF-1.7\nfixture\n"

    async def run():
        async with PdfDownloader(
            user_agent="Mneme/Test",
            request_interval_seconds=0,
            timeout_seconds=1,
            max_attempts=1,
            max_bytes=1024,
            transport=httpx.MockTransport(lambda request: httpx.Response(200, content=content)),
        ) as downloader:
            return await downloader.download(
                url=versioned_pdf_url("2607.00001", 1),
                destination=tmp_path / "source.pdf",
            )

    result = asyncio.run(run())

    assert result.path.read_bytes() == content
    assert result.byte_size == len(content)
    assert result.reused is False
