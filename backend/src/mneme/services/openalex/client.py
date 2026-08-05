"""Bounded OpenAlex access with strict arXiv identity verification."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from types import TracebackType
from typing import Self
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from mneme.core.config import Settings

_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
_ARXIV_PATH = re.compile(
    r"^/(?:abs|pdf)/(?P<base>(?:\d{4}\.\d{4,5}|[A-Za-z0-9._-]+/\d{7}))"
    r"(?:v[1-9]\d*)?(?:\.pdf)?/?$",
    re.IGNORECASE,
)
_WORK_SELECT = "id,display_name,locations,referenced_works"


class _OpenAlexLocation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    landing_page_url: str | None = None
    pdf_url: str | None = None


class _OpenAlexWork(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1)
    display_name: str = ""
    locations: list[_OpenAlexLocation] = Field(default_factory=list)
    referenced_works: list[str] = Field(default_factory=list)


class _OpenAlexPage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[_OpenAlexWork]


class OpenAlexClientError(RuntimeError):
    """A safe description of an OpenAlex transport or payload failure."""


class OpenAlexHTTPError(OpenAlexClientError):
    """OpenAlex returned a non-success status."""

    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"OpenAlex request failed with HTTP {status_code}")


@dataclass(frozen=True, slots=True)
class OpenAlexNeighborhood:
    """Real arXiv identities observed on both sides of one OpenAlex work."""

    references: tuple[str, ...]
    citations: tuple[str, ...]


class OpenAlexClient:
    """Resolve citation neighbors while accepting only verified arXiv locations."""

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._settings = settings
        self._sleep = sleep
        params: dict[str, str] = {}
        if settings.openalex_api_key is not None:
            params["api_key"] = settings.openalex_api_key.get_secret_value()
        self._client = httpx.AsyncClient(
            base_url=f"{str(settings.openalex_api_url).rstrip('/')}/",
            transport=transport,
            timeout=settings.openalex_timeout_seconds,
            headers={"User-Agent": settings.arxiv_user_agent},
            params=params,
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

    async def fetch_neighborhood(
        self,
        *,
        arxiv_id: str,
        title: str,
        limit: int,
    ) -> OpenAlexNeighborhood | None:
        """Return a bounded neighborhood after exact arXiv-location verification."""
        if not 1 <= limit <= 100:
            raise ValueError("OpenAlex neighbor limit must be between 1 and 100")
        center = await self._find_center(arxiv_id=arxiv_id, title=title)
        if center is None:
            return None

        reference_works = await self._fetch_reference_works(center.referenced_works[:100])
        citation_works = await self._list_works(
            {
                "filter": f"cites:{self._short_work_id(center.id)}",
                "per-page": "100",
                "select": _WORK_SELECT,
            }
        )
        return OpenAlexNeighborhood(
            references=self._verified_arxiv_ids(reference_works, arxiv_id, limit),
            citations=self._verified_arxiv_ids(citation_works, arxiv_id, limit),
        )

    async def _find_center(self, *, arxiv_id: str, title: str) -> _OpenAlexWork | None:
        exact = await self._list_works(
            {
                "filter": (f"locations.landing_page_url:https://arxiv.org/abs/{arxiv_id}"),
                "per-page": "5",
                "select": _WORK_SELECT,
            }
        )
        match = self._select_verified(exact, arxiv_id)
        if match is not None:
            return match
        searched = await self._list_works(
            {
                "search": title,
                "per-page": "25",
                "select": _WORK_SELECT,
            }
        )
        return self._select_verified(searched, arxiv_id)

    async def _fetch_reference_works(
        self,
        work_ids: list[str],
    ) -> tuple[_OpenAlexWork, ...]:
        if not work_ids:
            return ()
        short_ids = tuple(dict.fromkeys(self._short_work_id(value) for value in work_ids))
        return await self._list_works(
            {
                "filter": f"openalex:{'|'.join(short_ids)}",
                "per-page": str(len(short_ids)),
                "select": _WORK_SELECT,
            }
        )

    async def _list_works(self, params: dict[str, str]) -> tuple[_OpenAlexWork, ...]:
        response = await self._request_with_retries(params)
        if response.status_code != 200:
            raise OpenAlexHTTPError(response.status_code)
        try:
            page = _OpenAlexPage.model_validate(response.json())
        except (ValueError, ValidationError) as error:
            raise OpenAlexClientError("OpenAlex returned an invalid works page") from error
        return tuple(page.results)

    async def _request_with_retries(self, params: dict[str, str]) -> httpx.Response:
        for attempt in range(self._settings.openalex_max_attempts):
            try:
                response = await self._client.get("works", params=params)
            except httpx.TransportError as error:
                if attempt + 1 == self._settings.openalex_max_attempts:
                    raise OpenAlexClientError("OpenAlex request failed after retries") from error
                await self._sleep(2**attempt)
                continue
            if response.status_code not in _RETRYABLE_STATUS_CODES:
                return response
            if attempt + 1 == self._settings.openalex_max_attempts:
                raise OpenAlexHTTPError(response.status_code)
            await self._sleep(2**attempt)
        raise AssertionError("unreachable retry loop")

    @classmethod
    def _verified_arxiv_ids(
        cls,
        works: tuple[_OpenAlexWork, ...],
        center_arxiv_id: str,
        limit: int,
    ) -> tuple[str, ...]:
        ordered: list[str] = []
        seen = {center_arxiv_id}
        for work in works:
            arxiv_id = cls._work_arxiv_id(work)
            if arxiv_id is None or arxiv_id in seen:
                continue
            seen.add(arxiv_id)
            ordered.append(arxiv_id)
            if len(ordered) == limit:
                break
        return tuple(ordered)

    @classmethod
    def _select_verified(
        cls,
        works: tuple[_OpenAlexWork, ...],
        arxiv_id: str,
    ) -> _OpenAlexWork | None:
        return next((work for work in works if cls._work_arxiv_id(work) == arxiv_id), None)

    @classmethod
    def _work_arxiv_id(cls, work: _OpenAlexWork) -> str | None:
        for location in work.locations:
            for value in (location.landing_page_url, location.pdf_url):
                if value is None:
                    continue
                parsed = urlparse(value)
                if parsed.hostname not in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
                    continue
                match = _ARXIV_PATH.fullmatch(parsed.path)
                if match is not None:
                    return match.group("base")
        return None

    @staticmethod
    def _short_work_id(value: str) -> str:
        work_id = value.rstrip("/").rsplit("/", 1)[-1]
        if not re.fullmatch(r"W\d+", work_id):
            raise OpenAlexClientError("OpenAlex returned an invalid work identity")
        return work_id
