"""Single-connection, rate-limited access to the legacy arXiv API."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Self

import httpx

from mneme.core.config import Settings
from mneme.services.arxiv.parser import parse_arxiv_feed
from mneme.services.arxiv.types import ArxivFeed

CATEGORY_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(?:\.[A-Za-z0-9-]+)?$")
ARXIV_ID_PATTERN = re.compile(r"^(?:\d{4}\.\d{4,5}|[A-Za-z0-9._-]+/\d{7})(?:v[1-9]\d*)?$")
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
TOPIC_SEARCH_MAX_TERMS = 20


def _topic_search_clause(topic: str) -> str:
    """Return one field-scoped arXiv clause without exposing query syntax."""
    candidate = " ".join(topic.strip().split())
    if not candidate:
        raise ValueError("arXiv topics must not be empty")
    if len(candidate) > 100:
        raise ValueError("arXiv topics must not exceed 100 characters")
    # Dotted values are recognizable modern arXiv category identifiers. Plain
    # words such as ``hci`` remain natural-language searches rather than being
    # mistaken for legacy category names.
    if "." in candidate and CATEGORY_PATTERN.fullmatch(candidate) is not None:
        archive, subject = candidate.split(".", 1)
        canonical = f"{archive}.{subject.upper()}"
        if canonical != candidate:
            return f"(cat:{candidate} OR cat:{canonical})"
        return f"cat:{candidate}"
    escaped = candidate.replace("\\", "\\\\").replace('"', '\\"')
    return f'all:"{escaped}"'


def build_topic_search_query(topics: Sequence[str]) -> str:
    """Build a bounded OR query from categories and safely quoted phrases."""
    normalized = tuple(dict.fromkeys(item.strip() for item in topics if item.strip()))
    if not normalized:
        raise ValueError("At least one arXiv topic is required")
    if len(normalized) > TOPIC_SEARCH_MAX_TERMS:
        raise ValueError("arXiv topic count exceeds the bounded query size")
    clauses = tuple(_topic_search_clause(topic) for topic in normalized)
    return clauses[0] if len(clauses) == 1 else f"({' OR '.join(clauses)})"


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
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._wall_clock = wall_clock
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._last_request_started: float | None = None
        self._not_before = 0.0
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
            next_allowed = self._not_before
            if self._last_request_started is not None:
                next_allowed = max(
                    next_allowed,
                    self._last_request_started + self._settings.arxiv_request_interval_seconds,
                )
            delay = next_allowed - self._clock()
            if delay > 0:
                await self._sleep(delay)
            self._last_request_started = self._clock()
            return await self._client.get(str(self._settings.arxiv_api_url), params=params)

    def _defer(self, delay: float) -> None:
        self._not_before = max(self._not_before, self._clock() + delay)

    def _retry_after(self, response: httpx.Response) -> float | None:
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
            return max(0.0, (retry_at - self._wall_clock()).total_seconds())

    async def _request_with_retries(self, params: dict[str, str | int]) -> httpx.Response:
        for attempt in range(self._settings.arxiv_max_attempts):
            try:
                response = await self._request(params)
            except httpx.TransportError as exc:
                if attempt + 1 == self._settings.arxiv_max_attempts:
                    raise ArxivClientError("arXiv request failed after retries") from exc
                self._defer(2**attempt)
                continue
            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response
            if attempt + 1 == self._settings.arxiv_max_attempts:
                raise ArxivHTTPError(response.status_code)
            self._defer(max(2**attempt, self._retry_after(response) or 0.0))
        raise AssertionError("unreachable retry loop")

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

        response = await self._request_with_retries(
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

    async def fetch_by_topics(
        self,
        topics: Sequence[str],
        *,
        start: int = 0,
        max_results: int = 20,
    ) -> ArxivFeed:
        """Fetch newest papers for a bounded set of categories or topic phrases."""
        search_query = build_topic_search_query(topics)
        if start < 0:
            raise ValueError("start must be non-negative")
        if not 1 <= max_results <= self._settings.arxiv_max_results:
            raise ValueError("max_results exceeds the configured page size")
        response = await self._request_with_retries(
            {
                "search_query": search_query,
                "start": start,
                "max_results": max_results,
                "sortBy": "submittedDate",
                "sortOrder": "descending",
            }
        )
        if response.status_code != 200:
            raise ArxivHTTPError(response.status_code)
        return parse_arxiv_feed(response.content)

    async def fetch_by_id(self, arxiv_id: str) -> ArxivFeed:
        """Fetch the latest metadata for one validated arXiv identifier."""
        return await self.fetch_by_ids([arxiv_id])

    async def fetch_by_ids(self, arxiv_ids: Sequence[str]) -> ArxivFeed:
        """Fetch latest metadata for a bounded collection of arXiv identifiers."""
        normalized_ids = tuple(dict.fromkeys(item.strip() for item in arxiv_ids))
        if not normalized_ids:
            raise ValueError("At least one arXiv identifier is required")
        if len(normalized_ids) > self._settings.arxiv_max_results:
            raise ValueError("arXiv identifier count exceeds the configured page size")
        if any(
            len(arxiv_id) > 64 or ARXIV_ID_PATTERN.fullmatch(arxiv_id) is None
            for arxiv_id in normalized_ids
        ):
            raise ValueError("Invalid arXiv identifier")
        response = await self._request_with_retries(
            {
                "id_list": ",".join(normalized_ids),
                "max_results": len(normalized_ids),
            }
        )
        if response.status_code != 200:
            raise ArxivHTTPError(response.status_code)
        return parse_arxiv_feed(response.content)
