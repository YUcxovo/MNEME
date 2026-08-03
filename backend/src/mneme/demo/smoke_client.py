"""Typed HTTP client for the deployed MVP acceptance sequence."""

from __future__ import annotations

from typing import TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, ValidationError

from mneme.api.schemas.digests import Digest
from mneme.api.schemas.graphs import Graph
from mneme.api.schemas.jobs import Job
from mneme.api.schemas.papers import PaperPage
from mneme.api.schemas.preferences import Preferences
from mneme.api.schemas.qa import Answer, Question
from mneme.api.schemas.summaries import Summary
from mneme.demo.smoke_types import MvpSmokeError

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class LivenessPayload(BaseModel):
    """Expected public liveness payload."""

    model_config = ConfigDict(extra="forbid")
    status: str


class ReadinessDependenciesPayload(BaseModel):
    """Expected dependency states in a readiness payload."""

    model_config = ConfigDict(extra="forbid")
    postgresql: str
    redis: str


class ReadinessPayload(BaseModel):
    """Expected public readiness payload."""

    model_config = ConfigDict(extra="forbid")
    status: str
    dependencies: ReadinessDependenciesPayload


class MvpSmokeClient:
    """Exercise only the public HTTP surface used by the MVP client."""

    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_seconds: float,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._authorization = f"Bearer {token}"
        self._client = client or httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    async def liveness(self) -> LivenessPayload:
        return _validate(
            LivenessPayload, await self._request("GET", "/v1/health", "liveness"), "liveness"
        )

    async def readiness(self) -> ReadinessPayload:
        return _validate(
            ReadinessPayload,
            await self._request("GET", "/v1/health/ready", "readiness"),
            "readiness",
        )

    async def preferences(self) -> Preferences:
        return _validate(
            Preferences,
            await self._request("GET", "/v1/users/me/preferences", "preferences"),
            "preferences",
        )

    async def papers(self, *, cursor: str | None = None) -> PaperPage:
        params = {"limit": "50"}
        if cursor is not None:
            params["cursor"] = cursor
        return _validate(
            PaperPage,
            await self._request("GET", "/v1/papers", "catalog", params=params),
            "catalog",
        )

    async def summary(self, paper_id: UUID) -> Summary | Job:
        status_code, payload = await self._request_with_status(
            "GET", f"/v1/papers/{paper_id}/summary", "summary", expected={200, 202}
        )
        if status_code == 200:
            return _validate(Summary, payload, "summary")
        return _validate(Job, payload, "summary")

    async def job(self, job_id: UUID) -> Job:
        return _validate(Job, await self._request("GET", f"/v1/jobs/{job_id}", "job"), "job")

    async def recommended_digest(self) -> Digest:
        return _validate(
            Digest,
            await self._request("POST", "/v1/digests/recommended", "digest"),
            "digest",
        )

    async def graph(self, paper_id: UUID) -> Graph:
        return _validate(
            Graph,
            await self._request(
                "GET",
                f"/v1/graph/{paper_id}",
                "graph",
                params={"depth": "1", "limit": "50"},
            ),
            "graph",
        )

    async def ask(self, paper_id: UUID, question: str) -> Answer:
        payload = Question(question=question, paper_id=paper_id)
        return _validate(
            Answer,
            await self._request("POST", "/v1/qa/ask", "qa", json=payload.model_dump(mode="json")),
            "qa",
        )

    async def _request(
        self,
        method: str,
        path: str,
        operation: str,
        *,
        json: object | None = None,
        params: dict[str, str] | None = None,
    ) -> object:
        _, payload = await self._request_with_status(
            method, path, operation, expected={200}, json=json, params=params
        )
        return payload

    async def _request_with_status(
        self,
        method: str,
        path: str,
        operation: str,
        *,
        expected: set[int],
        json: object | None = None,
        params: dict[str, str] | None = None,
    ) -> tuple[int, object]:
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                params=params,
                headers={"Authorization": self._authorization},
            )
        except httpx.HTTPError as exception:
            raise MvpSmokeError(operation, "request_failed", operation=operation) from exception
        if response.status_code not in expected:
            raise MvpSmokeError(
                operation,
                "unexpected_http_status",
                operation=operation,
                status_code=response.status_code,
            )
        try:
            return response.status_code, response.json()
        except ValueError as exception:
            raise MvpSmokeError(operation, "invalid_json", operation=operation) from exception

    async def aclose(self) -> None:
        await self._client.aclose()


def _validate(model: type[_ModelT], payload: object, operation: str) -> _ModelT:
    try:
        return model.model_validate(payload)
    except ValidationError as exception:
        raise MvpSmokeError(
            operation, "invalid_response_schema", operation=operation
        ) from exception
