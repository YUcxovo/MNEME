"""Tests for OpenAlex citation access and strict arXiv identity matching."""

import asyncio

import httpx
import pytest

from mneme.core.config import Settings
from mneme.services.openalex import OpenAlexClient, OpenAlexHTTPError


def _work(
    work_id: str,
    arxiv_id: str | None,
    *,
    references: list[str] | None = None,
) -> dict[str, object]:
    locations: list[dict[str, str]] = []
    if arxiv_id is not None:
        locations.append(
            {
                "landing_page_url": f"https://arxiv.org/abs/{arxiv_id}",
                "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}.pdf",
            }
        )
    return {
        "id": f"https://openalex.org/{work_id}",
        "display_name": f"Work {work_id}",
        "locations": locations,
        "referenced_works": references or [],
    }


@pytest.mark.base
@pytest.mark.pipeline
def test_neighborhood_keeps_only_arxiv_verified_reference_and_citation_works() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        query_filter = request.url.params.get("filter", "")
        if query_filter.startswith("locations.landing_page_url"):
            return httpx.Response(
                200,
                json={"results": [_work("W1", "1706.03762", references=["W2", "W4"])]},
            )
        if query_filter.startswith("openalex:"):
            return httpx.Response(
                200,
                json={"results": [_work("W2", "1810.04805v2"), _work("W4", None)]},
            )
        if query_filter == "cites:W1":
            return httpx.Response(
                200,
                json={"results": [_work("W3", "2005.14165"), _work("W5", None)]},
            )
        raise AssertionError(f"unexpected OpenAlex request: {request.url}")

    async def exercise():
        async with OpenAlexClient(
            Settings(_env_file=None),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.fetch_neighborhood(
                arxiv_id="1706.03762",
                title="Attention Is All You Need",
                limit=20,
            )

    result = asyncio.run(exercise())

    assert result is not None
    assert result.references == ("1810.04805",)
    assert result.citations == ("2005.14165",)
    assert len(requests) == 3


@pytest.mark.base
@pytest.mark.pipeline
def test_title_search_never_accepts_a_work_without_the_exact_arxiv_location() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.params.get("search"):
            return httpx.Response(200, json={"results": [_work("W9", "1706.00001")]})
        return httpx.Response(200, json={"results": []})

    async def exercise():
        async with OpenAlexClient(
            Settings(_env_file=None),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.fetch_neighborhood(
                arxiv_id="1706.03762",
                title="Attention Is All You Need",
                limit=20,
            )

    assert asyncio.run(exercise()) is None
    assert len(requests) == 2
    assert requests[1].url.params["search"] == "Attention Is All You Need"


@pytest.mark.base
@pytest.mark.pipeline
def test_retryable_openalex_failure_is_bounded() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(429)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def exercise() -> None:
        async with OpenAlexClient(
            Settings(openalex_max_attempts=2, _env_file=None),
            transport=httpx.MockTransport(handler),
            sleep=sleep,
        ) as client:
            with pytest.raises(OpenAlexHTTPError) as captured:
                await client.fetch_neighborhood(
                    arxiv_id="1706.03762",
                    title="Attention Is All You Need",
                    limit=20,
                )
            assert captured.value.status_code == 429

    asyncio.run(exercise())
    assert attempts == 2
    assert delays == [1]
