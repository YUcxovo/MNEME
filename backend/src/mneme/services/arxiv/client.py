"""Single-connection, rate-limited access to the legacy arXiv API."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from types import TracebackType
from typing import Self

import httpx

from mneme.core.config import Settings
from mneme.services.arxiv.parser import parse_arxiv_feed
from mneme.services.arxiv.types import ArxivFeed

CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[A-Za-z0-9-]+)?$")


class ArxivClientError(RuntimeError):
    """A safe public description of an arXiv transport failure."""


class ArxivHTTPError(ArxivClientError):
    """arXiv returned a non-success HTTP status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"arXiv request failed with HTTP {status_code}")


class ArxivClient:
    """Fetch Atom pages while honoring one connection and one request per interval."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request_started: float | None = None
        self._client = httpx.AsyncClient(
            transport=transport,
            timeout=settings.arxiv_timeout_seconds,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            headers={"User-Agent": settings.arxiv_user_agent},
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

    @property
    def is_closed(self) -> bool:
        """Whether the underlying HTTP client has been closed."""
        return self._client.is_closed

    async def aclose(self) -> None:
        """Close the underlying HTTP connection pool."""
        await self._client.aclose()

    async def _request(self, params: dict[str, str | int]) -> httpx.Response:
        async with self._lock:
            if self._last_request_started is not None:
                elapsed = self._clock() - self._last_request_started
                delay = self._settings.arxiv_request_interval_seconds - elapsed
                if delay > 0:
                    await self._sleep(delay)
            self._last_request_started = self._clock()
            return await self._client.get(str(self._settings.arxiv_api_url), params=params)

    async def fetch_by_category(
        self, category: str, *, start: int = 0, max_results: int = 20
    ) -> ArxivFeed:
        """Fetch newest-first metadata for one validated arXiv category."""
        if len(category) > 64 or CATEGORY_PATTERN.fullmatch(category) is None:
            raise ValueError("Invalid arXiv category")
        if start < 0:
            raise ValueError("start must be non-negative")
        if not 1 <= max_results <= self._settings.arxiv_max_results:
            raise ValueError("max_results exceeds the configured page size")

        response = await self._request(
            {
                "search_query": f"cat:{category}",
                "start": start,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        if response.status_code != 200:
            raise ArxivHTTPError(response.status_code)
        return parse_arxiv_feed(response.content)
