"""Resumable orchestration for installation-local production demo state."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Protocol, TypeVar
from uuid import UUID

from mneme.api.schemas.events import EventIngestionResult, UserEvent
from mneme.api.schemas.onboarding import SeedInitializationResult
from mneme.api.schemas.papers import Paper
from mneme.api.schemas.preferences import Preferences, PreferenceUpdate
from mneme.core.config import Settings
from mneme.demo.client import DemoSeedClient, DemoSeedRemoteError
from mneme.demo.manifest import DemoSeedManifest
from mneme.demo.seeding_support import (
    DemoSeedConfig,
    DemoSeedError,
    DemoSeedResult,
    bootstrap_demo_user,
    demo_seed_lock,
)
from mneme.demo.state import verify_persisted_seed_state
from mneme.models.paper import ProcessingStatus
from mneme.repositories.demo_user_bootstrap import DemoUserBootstrapResult

_T = TypeVar("_T")


class DemoSeedOperations(Protocol):
    """Typed HTTP operations used by the orchestration layer."""

    async def initialize(self, arxiv_reference: str) -> SeedInitializationResult: ...

    async def get_paper(self, paper_id: UUID) -> Paper: ...

    async def replace_preferences(self, update: PreferenceUpdate) -> Preferences: ...

    async def ingest_events(self, events: list[UserEvent]) -> EventIngestionResult: ...

    async def aclose(self) -> None: ...


async def seed_demo(
    settings: Settings,
    manifest: DemoSeedManifest,
    config: DemoSeedConfig,
    *,
    token: str,
    client: DemoSeedOperations | None = None,
    bootstrapper: Callable[
        [Settings, str], Awaitable[DemoUserBootstrapResult]
    ] = bootstrap_demo_user,
    state_verifier: Callable[
        [Settings, DemoSeedManifest, list[UserEvent]], Awaitable[UUID]
    ] = verify_persisted_seed_state,
) -> DemoSeedResult:
    """Bootstrap, initialize, wait for usable papers, then replay deterministic events."""
    resolved_client = client or DemoSeedClient(
        base_url=config.base_url,
        token=token,
        timeout_seconds=config.request_timeout_seconds,
    )
    operation_succeeded = False
    try:
        async with demo_seed_lock(config.lock_file):
            bootstrap = await bootstrapper(settings, manifest.display_name)
            initialization = await _translate_remote(
                resolved_client.initialize(manifest.seed_arxiv_reference)
            )
            entries_by_rank = {entry.rank: entry for entry in initialization.digest.entries}
            if set(entries_by_rank) != set(range(1, manifest.onboarding_limit + 1)):
                raise DemoSeedError("Seed onboarding returned an incomplete digest")
            ready_papers, partial_papers = await _wait_until_usable(
                resolved_client,
                tuple(entry.paper.id for entry in entries_by_rank.values()),
                timeout_seconds=config.ready_timeout_seconds,
                poll_interval_seconds=config.poll_interval_seconds,
            )
            preferences = await _translate_remote(
                resolved_client.replace_preferences(
                    PreferenceUpdate(
                        topics=manifest.topics,
                        followed_authors=manifest.followed_authors,
                    )
                )
            )
            if (
                preferences.topics != manifest.topics
                or preferences.followed_authors != manifest.followed_authors
            ):
                raise DemoSeedError("Stored demo preferences did not match the manifest")
            events = [
                UserEvent(
                    event_id=manifest.event_id(template),
                    event_type=template.event_type,
                    paper_id=entries_by_rank[template.paper_rank].paper.id,
                    occurred_at=manifest.event_time(template, initialization.digest.generated_at),
                    duration_ms=template.duration_ms,
                    context={
                        "manifest_id": manifest.manifest_id,
                        "manifest_sha256": manifest.content_sha256(),
                        "source": "demo_seed",
                    },
                )
                for template in manifest.events
            ]
            ingestion = await _translate_remote(resolved_client.ingest_events(events))
            if ingestion.accepted + ingestion.duplicates != len(events):
                raise DemoSeedError("Demo event ingestion returned inconsistent counts")
            seed_paper_id = await state_verifier(settings, manifest, events)
            ordered_entries = tuple(entries_by_rank[rank] for rank in sorted(entries_by_rank))
            result = DemoSeedResult(
                manifest_id=manifest.manifest_id,
                manifest_sha256=manifest.content_sha256(),
                digest_id=str(initialization.digest.id),
                seed_paper_id=str(seed_paper_id),
                digest_paper_ids=tuple(str(entry.paper.id) for entry in ordered_entries),
                digest_arxiv_ids=tuple(entry.paper.arxiv_id for entry in ordered_entries),
                paper_count=len(entries_by_rank),
                ready_papers=ready_papers,
                partial_papers=partial_papers,
                events_accepted=ingestion.accepted,
                events_duplicates=ingestion.duplicates,
                user_created=bootstrap.user_created,
                preferences_created=bootstrap.preferences_created,
            )
            operation_succeeded = True
            return result
    finally:
        try:
            await resolved_client.aclose()
        except Exception as exception:
            if operation_succeeded:
                raise DemoSeedError("Demo seed client did not close cleanly") from exception


async def _wait_until_usable(
    client: DemoSeedOperations,
    paper_ids: tuple[UUID, ...],
    *,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> tuple[int, int]:
    try:
        async with asyncio.timeout(timeout_seconds):
            statuses: dict[UUID, ProcessingStatus] = {}
            pending = set(paper_ids)
            while pending:
                for paper_id in tuple(pending):
                    paper = await _translate_remote(client.get_paper(paper_id))
                    if paper.processing_status is ProcessingStatus.FAILED:
                        raise DemoSeedError("A demo paper failed during preparation")
                    if paper.processing_status in {
                        ProcessingStatus.READY,
                        ProcessingStatus.PARTIAL,
                    }:
                        statuses[paper_id] = paper.processing_status
                        pending.remove(paper_id)
                if pending:
                    await asyncio.sleep(poll_interval_seconds)
            ready = sum(status is ProcessingStatus.READY for status in statuses.values())
            partial = sum(status is ProcessingStatus.PARTIAL for status in statuses.values())
            return ready, partial
    except TimeoutError as exception:
        raise DemoSeedError("Demo papers did not become usable before the deadline") from exception


async def _translate_remote(awaitable: Awaitable[_T]) -> _T:
    try:
        return await awaitable
    except DemoSeedRemoteError as exception:
        raise DemoSeedError(f"Demo seed stage {exception.operation} failed") from exception
