"""Tests for bounded and rate-aware Semantic Scholar graph access."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest

from mneme.core.config import Settings
from mneme.services.semantic_scholar import (
    CitationDirection,
    SemanticPaper,
    SemanticScholarClient,
    SemanticScholarClientError,
    SemanticScholarHTTPError,
)


class FakeTime:
    """Monotonic and wall clocks advanced by asynchronous sleep."""

    def __init__(self) -> None:
        self.value = 0.0
        self.delays: list[float] = []

    def clock(self) -> float:
        return self.value

    def wall_clock(self) -> datetime:
        return datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self.value)

    async def sleep(self, delay: float) -> None:
        self.delays.append(delay)
        self.value += delay


def _settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "semantic_scholar_api_url": "https://example.test/graph/v1",
        "semantic_scholar_request_interval_seconds": 0,
    }
    values.update(overrides)
    return Settings.model_validate(values)


@pytest.mark.base
@pytest.mark.pipeline
def test_paper_batch_chunking_key_and_arxiv_normalization() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        ids = json.loads(request.content)["ids"]
        return httpx.Response(
            200,
            json=[
                {
                    "paperId": f"s2-{paper_id}",
                    "externalIds": {
                        "ArXiv": paper_id.removeprefix("ARXIV:") + "v2",
                        "CorpusId": 123,
                    },
                }
                for paper_id in ids
            ],
        )

    async def exercise() -> tuple[str | None, ...]:
        async with SemanticScholarClient(
            _settings(semantic_scholar_api_key="secret", semantic_scholar_batch_size=2),
            transport=httpx.MockTransport(handler),
        ) as client:
            papers = await client.fetch_papers(
                ["ARXIV:2401.00001", "ARXIV:2401.00002", "ARXIV:2401.00003"]
            )
            return tuple(paper.arxiv_id for paper in papers)

    assert asyncio.run(exercise()) == (
        "2401.00001",
        "2401.00002",
        "2401.00003",
    )
    assert len(requests) == 2
    assert all(request.headers["x-api-key"] == "secret" for request in requests)
    assert all(request.url.params["fields"] == "externalIds" for request in requests)


@pytest.mark.base
@pytest.mark.pipeline
@pytest.mark.parametrize(
    ("direction", "nested_key"),
    [
        (CitationDirection.CITATIONS, "citingPaper"),
        (CitationDirection.REFERENCES, "citedPaper"),
    ],
)
def test_neighbor_pagination_uses_direction_and_server_next(
    direction: CitationDirection, nested_key: str
) -> None:
    offsets: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        offsets.append(offset)
        if offset == 0:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {nested_key: {"paperId": "one", "externalIds": None}},
                        {nested_key: None},
                    ],
                    "next": 7,
                },
            )
        return httpx.Response(
            200,
            json={
                "data": [{nested_key: {"paperId": "two", "externalIds": {}}}],
            },
        )

    async def exercise() -> tuple[str, ...]:
        async with SemanticScholarClient(
            _settings(semantic_scholar_page_size=2),
            transport=httpx.MockTransport(handler),
        ) as client:
            papers = await client.fetch_neighbors("center/id", direction, limit=2)
            return tuple(paper.paper_id for paper in papers)

    assert asyncio.run(exercise()) == ("one", "two")
    assert offsets == [0, 7]


@pytest.mark.base
@pytest.mark.pipeline
def test_paper_references_are_fetched_in_one_bounded_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "paperId": "s2-center",
                "externalIds": {"ArXiv": "1706.03762", "CorpusId": 13756489},
                "references": [
                    {
                        "paperId": f"s2-reference-{index}",
                        "externalIds": {"ArXiv": f"1705.0000{index}"},
                    }
                    for index in range(1, 5)
                ]
                + [{"paperId": None, "externalIds": {"ArXiv": "invalid"}}],
            },
        )

    async def exercise() -> tuple[SemanticPaper, tuple[SemanticPaper, ...]]:
        async with SemanticScholarClient(
            _settings(),
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.fetch_paper_references("ARXIV:1706.03762", limit=3)

    center, references = asyncio.run(exercise())
    assert center.arxiv_id == "1706.03762"
    assert [paper.arxiv_id for paper in references] == [
        "1705.00001",
        "1705.00002",
        "1705.00003",
    ]
    assert len(requests) == 1
    assert requests[0].url.path.endswith("/paper/ARXIV:1706.03762")
    assert requests[0].url.params["fields"] == "externalIds,references.externalIds"


@pytest.mark.base
@pytest.mark.pipeline
def test_retry_after_http_date_and_client_closure() -> None:
    timer = FakeTime()
    attempts = 0
    retry_at = format_datetime(timer.wall_clock() + timedelta(seconds=6), usegmt=True)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": retry_at})
        return httpx.Response(200, json=[])

    async def exercise() -> bool:
        client = SemanticScholarClient(
            _settings(semantic_scholar_max_attempts=2),
            transport=httpx.MockTransport(handler),
            clock=timer.clock,
            wall_clock=timer.wall_clock,
            sleep=timer.sleep,
        )
        await client.fetch_papers(["ARXIV:2401.00001"])
        await client.aclose()
        return client.is_closed

    assert asyncio.run(exercise())
    assert attempts == 2
    assert timer.delays == [6.0]


@pytest.mark.base
@pytest.mark.pipeline
def test_transport_retry_exhaustion_is_safe() -> None:
    timer = FakeTime()

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("private transport details", request=request)

    async def exercise() -> None:
        async with SemanticScholarClient(
            _settings(semantic_scholar_max_attempts=2),
            transport=httpx.MockTransport(handler),
            clock=timer.clock,
            sleep=timer.sleep,
        ) as client:
            with pytest.raises(SemanticScholarClientError, match="request failed after retries"):
                await client.fetch_papers(["ARXIV:2401.00001"])

    asyncio.run(exercise())
    assert timer.delays == [1.0]


@pytest.mark.base
@pytest.mark.pipeline
def test_non_success_invalid_payload_and_non_advancing_cursor_are_rejected() -> None:
    async def exercise() -> None:
        async with SemanticScholarClient(
            _settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(400)),
        ) as client:
            with pytest.raises(SemanticScholarHTTPError, match="HTTP 400"):
                await client.fetch_papers(["ARXIV:2401.00001"])

        async with SemanticScholarClient(
            _settings(),
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={})),
        ) as client:
            with pytest.raises(SemanticScholarClientError, match="invalid paper batch"):
                await client.fetch_papers(["ARXIV:2401.00001"])

        async with SemanticScholarClient(
            _settings(),
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": [], "next": 0})
            ),
        ) as client:
            with pytest.raises(SemanticScholarClientError, match="non-advancing"):
                await client.fetch_neighbors("center", CitationDirection.REFERENCES, limit=1)

    asyncio.run(exercise())
