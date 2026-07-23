"""Serialized, retrying access to Semantic Scholar citation data."""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Self
from urllib.parse import quote

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from mneme.core.config import Settings
from mneme.services.semantic_scholar.types import CitationDirection, SemanticPaper

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_BATCH_RESPONSE = TypeAdapter(list[SemanticPaper | None])


class _NeighborPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    data: list[dict[str, object]]
    next: int | None = None


class SemanticScholarClientError(RuntimeError):
    """A safe description of an upstream transport or payload failure."""


class SemanticScholarHTTPError(SemanticScholarClientError):
    """Semantic Scholar returned a non-success status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"Semantic Scholar request failed with HTTP {status_code}")


class SemanticScholarClient:
    """Fetch batched identities and paginated citation neighbors."""

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
        api_key = settings.semantic_scholar_api_key
        headers = {"User-Agent": settings.arxiv_user_agent}
        if api_key is not None:
            headers["x-api-key"] = api_key.get_secret_value()
        self._client = httpx.AsyncClient(
            base_url=f"{str(settings.semantic_scholar_api_url).rstrip('/')}/",
            transport=transport,
            timeout=settings.semantic_scholar_timeout_seconds,
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
            headers=headers,
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
        """Whether the HTTP connection pool has been closed."""
        return self._client.is_closed

    async def aclose(self) -> None:
        """Close the HTTP connection pool."""
        await self._client.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> httpx.Response:
        async with self._lock:
            next_allowed = self._not_before
            if self._last_request_started is not None:
                next_allowed = max(
                    next_allowed,
                    self._last_request_started
                    + self._settings.semantic_scholar_request_interval_seconds,
                )
            delay = next_allowed - self._clock()
            if delay > 0:
                await self._sleep(delay)
            self._last_request_started = self._clock()
            return await self._client.request(method, path, params=params, json=json_body)

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

    async def _request_with_retries(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, str | int] | None = None,
        json_body: dict[str, object] | None = None,
    ) -> httpx.Response:
        for attempt in range(self._settings.semantic_scholar_max_attempts):
            try:
                response = await self._request(method, path, params=params, json_body=json_body)
            except httpx.TransportError as exc:
                if attempt + 1 == self._settings.semantic_scholar_max_attempts:
                    raise SemanticScholarClientError(
                        "Semantic Scholar request failed after retries"
                    ) from exc
                self._defer(2**attempt)
                continue
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                return response
            if attempt + 1 == self._settings.semantic_scholar_max_attempts:
                raise SemanticScholarHTTPError(response.status_code)
            self._defer(max(2**attempt, self._retry_after(response) or 0.0))
        raise AssertionError("unreachable retry loop")

    @staticmethod
    def _require_success(response: httpx.Response) -> None:
        if response.status_code != 200:
            raise SemanticScholarHTTPError(response.status_code)

    async def fetch_papers(self, paper_ids: Sequence[str]) -> tuple[SemanticPaper, ...]:
        """Resolve provider-supported paper IDs in batches of at most 500."""
        unique_ids = tuple(dict.fromkeys(paper_ids))
        if any(not paper_id or len(paper_id) > 200 for paper_id in unique_ids):
            raise ValueError("Semantic Scholar paper IDs must contain 1 to 200 characters")

        papers: list[SemanticPaper] = []
        batch_size = self._settings.semantic_scholar_batch_size
        for start in range(0, len(unique_ids), batch_size):
            response = await self._request_with_retries(
                "POST",
                "paper/batch",
                params={"fields": "externalIds"},
                json_body={"ids": list(unique_ids[start : start + batch_size])},
            )
            self._require_success(response)
            try:
                batch = _BATCH_RESPONSE.validate_python(response.json())
            except (ValueError, ValidationError) as exc:
                raise SemanticScholarClientError(
                    "Semantic Scholar returned an invalid paper batch"
                ) from exc
            papers.extend(paper for paper in batch if paper is not None)
        return tuple(papers)

    async def fetch_neighbors(
        self,
        paper_id: str,
        direction: CitationDirection,
        *,
        limit: int,
    ) -> tuple[SemanticPaper, ...]:
        """Fetch one bounded citations or references collection using server cursors."""
        if not paper_id or len(paper_id) > 200:
            raise ValueError("Semantic Scholar paper ID must contain 1 to 200 characters")
        if not 1 <= limit <= self._settings.semantic_scholar_max_neighbors:
            raise ValueError("Neighbor limit exceeds the configured maximum")

        encoded_id = quote(paper_id, safe="")
        offset = 0
        papers: dict[str, SemanticPaper] = {}
        while len(papers) < limit:
            page_size = min(
                self._settings.semantic_scholar_page_size,
                limit - len(papers),
            )
            response = await self._request_with_retries(
                "GET",
                f"paper/{encoded_id}/{direction.value}",
                params={"fields": "externalIds", "offset": offset, "limit": page_size},
            )
            self._require_success(response)
            try:
                page = _NeighborPage.model_validate(response.json())
                for item in page.data:
                    nested = item.get(direction.nested_paper_key)
                    if nested is None:
                        continue
                    paper = SemanticPaper.model_validate(nested)
                    papers.setdefault(paper.paper_id, paper)
            except (ValueError, ValidationError) as exc:
                raise SemanticScholarClientError(
                    "Semantic Scholar returned an invalid neighbor page"
                ) from exc
            if page.next is None:
                break
            if page.next <= offset:
                raise SemanticScholarClientError(
                    "Semantic Scholar returned a non-advancing page cursor"
                )
            offset = page.next
        return tuple(papers.values())[:limit]
