"""Tests for serialized and rate-limited arXiv HTTP access."""

import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from pathlib import Path

import httpx
import pytest

from mneme.core.config import Settings
from mneme.services.arxiv import ArxivClient, ArxivHTTPError

FEED = (Path(__file__).parent / "fixtures" / "arxiv" / "empty_feed.xml").read_bytes()


class FakeTime:
    """Monotonic clock advanced by its asynchronous sleep function."""

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


@pytest.mark.pipeline
def test_category_query_and_user_agent() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=FEED)

    async def exercise() -> None:
        settings = Settings(_env_file=None)
        async with ArxivClient(settings, transport=httpx.MockTransport(handler)) as client:
            await client.fetch_by_category("cs.AI", start=10, max_results=5)

    asyncio.run(exercise())
    request = requests[0]
    assert request.url.params["search_query"] == "cat:cs.AI"
    assert request.url.params["start"] == "10"
    assert request.url.params["sortBy"] == "submittedDate"
    assert request.headers["User-Agent"].startswith("Mneme/0.1")


@pytest.mark.pipeline
def test_id_query_uses_arxiv_id_list() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=FEED)

    async def exercise() -> None:
        settings = Settings(_env_file=None)
        async with ArxivClient(settings, transport=httpx.MockTransport(handler)) as client:
            await client.fetch_by_id("2607.01234")

    asyncio.run(exercise())
    request = requests[0]
    assert request.url.params["id_list"] == "2607.01234"
    assert request.url.params["max_results"] == "1"
    assert "search_query" not in request.url.params


@pytest.mark.pipeline
def test_id_query_batches_unique_identifiers() -> None:
    requests: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=FEED)

    async def exercise() -> None:
        settings = Settings(_env_file=None)
        async with ArxivClient(settings, transport=httpx.MockTransport(handler)) as client:
            await client.fetch_by_ids(
                ["2607.01234", "2607.01235", "2607.01234"],
            )

    asyncio.run(exercise())
    request = requests[0]
    assert request.url.params["id_list"] == "2607.01234,2607.01235"
    assert request.url.params["max_results"] == "2"


@pytest.mark.pipeline
def test_invalid_arxiv_id_is_rejected_before_request() -> None:
    async def exercise() -> None:
        client = ArxivClient(
            Settings(_env_file=None),
            transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        )
        try:
            with pytest.raises(ValueError, match="Invalid arXiv identifier"):
                await client.fetch_by_id("not an arxiv id")
            with pytest.raises(ValueError, match="At least one"):
                await client.fetch_by_ids([])
        finally:
            await client.aclose()

    asyncio.run(exercise())


@pytest.mark.pipeline
def test_concurrent_calls_are_serial_and_rate_limited() -> None:
    timer = FakeTime()
    in_flight = 0
    maximum_in_flight = 0

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal in_flight, maximum_in_flight
        in_flight += 1
        maximum_in_flight = max(maximum_in_flight, in_flight)
        await asyncio.sleep(0)
        in_flight -= 1
        return httpx.Response(200, content=FEED)

    async def exercise() -> None:
        settings = Settings(_env_file=None)
        async with ArxivClient(
            settings,
            transport=httpx.MockTransport(handler),
            clock=timer.clock,
            sleep=timer.sleep,
        ) as client:
            await asyncio.gather(
                client.fetch_by_category("cs.AI"),
                client.fetch_by_category("cs.CL"),
            )

    asyncio.run(exercise())
    assert maximum_in_flight == 1
    assert timer.delays == [3.0]


@pytest.mark.pipeline
@pytest.mark.parametrize(
    ("category", "start", "max_results"),
    [("bad category", 0, 20), ("cs.AI", -1, 20), ("cs.AI", 0, 101)],
)
def test_invalid_query_is_rejected(category: str, start: int, max_results: int) -> None:
    async def exercise() -> None:
        client = ArxivClient(
            Settings(_env_file=None),
            transport=httpx.MockTransport(lambda _: httpx.Response(500)),
        )
        try:
            with pytest.raises(ValueError):
                await client.fetch_by_category(category, start=start, max_results=max_results)
        finally:
            await client.aclose()

    asyncio.run(exercise())


@pytest.mark.pipeline
def test_non_success_status_is_safe_and_client_closes() -> None:
    async def exercise() -> None:
        transport = httpx.MockTransport(lambda _: httpx.Response(400))
        client = ArxivClient(Settings(_env_file=None), transport=transport)
        with pytest.raises(ArxivHTTPError, match="HTTP 400") as captured:
            await client.fetch_by_category("cs.AI")
        assert captured.value.status_code == 400
        await client.aclose()
        assert client.is_closed

    asyncio.run(exercise())


@pytest.mark.pipeline
def test_retryable_status_obeys_retry_after_http_date() -> None:
    timer = FakeTime()
    attempts = 0
    retry_at = format_datetime(timer.wall_clock() + timedelta(seconds=7), usegmt=True)

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": retry_at})
        return httpx.Response(200, content=FEED)

    async def exercise() -> None:
        async with ArxivClient(
            Settings(arxiv_max_attempts=2, _env_file=None),
            transport=httpx.MockTransport(handler),
            clock=timer.clock,
            wall_clock=timer.wall_clock,
            sleep=timer.sleep,
        ) as client:
            await client.fetch_by_category("cs.AI")

    asyncio.run(exercise())
    assert attempts == 2
    assert timer.delays == [7.0]


@pytest.mark.pipeline
def test_transport_error_retries_then_succeeds() -> None:
    timer = FakeTime()
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("offline", request=request)
        return httpx.Response(200, content=FEED)

    async def exercise() -> None:
        async with ArxivClient(
            Settings(arxiv_max_attempts=2, _env_file=None),
            transport=httpx.MockTransport(handler),
            clock=timer.clock,
            sleep=timer.sleep,
        ) as client:
            await client.fetch_by_category("cs.AI")

    asyncio.run(exercise())
    assert attempts == 2
    assert timer.delays == [3.0]


@pytest.mark.pipeline
def test_retry_exhaustion_and_non_retryable_status() -> None:
    async def exercise() -> None:
        attempts = 0

        def unavailable(_: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503)

        timer = FakeTime()
        async with ArxivClient(
            Settings(arxiv_max_attempts=2, _env_file=None),
            transport=httpx.MockTransport(unavailable),
            clock=timer.clock,
            sleep=timer.sleep,
        ) as client:
            with pytest.raises(ArxivHTTPError) as captured:
                await client.fetch_by_category("cs.AI")
            assert captured.value.status_code == 503
        assert attempts == 2

        calls = 0

        def bad_request(_: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            return httpx.Response(400)

        async with ArxivClient(
            Settings(_env_file=None), transport=httpx.MockTransport(bad_request)
        ) as client:
            with pytest.raises(ArxivHTTPError):
                await client.fetch_by_category("cs.AI")
        assert calls == 1

    asyncio.run(exercise())
