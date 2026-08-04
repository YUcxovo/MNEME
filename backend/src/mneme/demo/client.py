"""Authenticated HTTP client for the existing demo preparation contracts."""

from __future__ import annotations

from typing import TypeVar
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError

from mneme.api.schemas.events import EventIngestionResult, UserEvent
from mneme.api.schemas.onboarding import SeedInitializationResult
from mneme.api.schemas.papers import Paper
from mneme.api.schemas.preferences import Preferences, PreferenceUpdate

_ModelT = TypeVar("_ModelT", bound=BaseModel)


class DemoSeedRemoteError(RuntimeError):
    """A demo preparation endpoint failed without exposing its response body."""

    def __init__(self, operation: str, status_code: int | None = None) -> None:
        super().__init__(f"Demo seed operation {operation} failed")
        self.operation = operation
        self.status_code = status_code


class DemoSeedClient:
    """Small typed client that exercises the same contracts as Android."""

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
        )

    async def initialize(self, arxiv_reference: str) -> SeedInitializationResult:
        payload = await self._request(
            "POST",
            "/v1/onboarding/seed",
            operation="onboarding",
            json={"arxiv_reference": arxiv_reference},
        )
        return _validate(SeedInitializationResult, payload, "onboarding")

    async def get_paper(self, paper_id: UUID) -> Paper:
        payload = await self._request("GET", f"/v1/papers/{paper_id}", operation="paper_status")
        return _validate(Paper, payload, "paper_status")

    async def replace_preferences(self, update: PreferenceUpdate) -> Preferences:
        payload = await self._request(
            "PUT",
            "/v1/users/me/preferences",
            operation="preferences",
            json=update.model_dump(mode="json"),
        )
        return _validate(Preferences, payload, "preferences")

    async def ingest_events(self, events: list[UserEvent]) -> EventIngestionResult:
        payload = await self._request(
            "POST",
            "/v1/events",
            operation="events",
            json=[event.model_dump(mode="json") for event in events],
        )
        return _validate(EventIngestionResult, payload, "events")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        json: object | None = None,
    ) -> object:
        try:
            response = await self._client.request(
                method,
                path,
                json=json,
                headers={"Authorization": self._authorization},
            )
        except httpx.HTTPError as exception:
            raise DemoSeedRemoteError(operation) from exception
        if response.status_code != 200:
            raise DemoSeedRemoteError(operation, response.status_code)
        try:
            return response.json()
        except ValueError as exception:
            raise DemoSeedRemoteError(operation, response.status_code) from exception

    async def aclose(self) -> None:
        await self._client.aclose()


def _validate(model: type[_ModelT], payload: object, operation: str) -> _ModelT:
    try:
        return model.model_validate(payload)
    except ValidationError as exception:
        raise DemoSeedRemoteError(operation, 200) from exception
