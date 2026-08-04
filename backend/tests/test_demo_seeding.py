"""Tests for resumable deterministic demo orchestration."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from mneme.api.schemas.digests import Digest, DigestEntry
from mneme.api.schemas.events import EventIngestionResult, UserEvent
from mneme.api.schemas.onboarding import SeedInitializationResult
from mneme.api.schemas.papers import Paper
from mneme.api.schemas.preferences import Preferences, PreferenceUpdate
from mneme.core.config import Settings
from mneme.core.security import token_sha256
from mneme.demo.manifest import DemoSeedManifest, load_default_demo_seed_manifest
from mneme.demo.seeding import seed_demo
from mneme.demo.seeding_support import (
    DemoSeedConfig,
    DemoSeedConfigurationError,
    DemoSeedError,
    demo_seed_lock,
    read_private_demo_token,
)
from mneme.models.digest import DigestType
from mneme.models.paper import ProcessingStatus
from mneme.repositories.demo_user_bootstrap import DemoUserBootstrapResult

ANCHOR = datetime(2026, 8, 3, 12, tzinfo=UTC)
USER_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
PAPER_IDS = tuple(UUID(int=index) for index in range(1, 6))
SEED_PAPER_ID = UUID(int=100)


def _settings(token: str = "demo-secret") -> Settings:
    return Settings(
        demo_user_id=USER_ID,
        demo_token_sha256=token_sha256(token),
        _env_file=None,
    )


def _initialization() -> SeedInitializationResult:
    entries = [
        DigestEntry.model_construct(
            paper=Paper.model_construct(
                id=paper_id,
                arxiv_id=f"2401.{rank:05d}",
                processing_status=ProcessingStatus.PARTIAL,
            ),
            rank=rank,
            relevance_score=1.0,
            recommendation_reason="seed",
        )
        for rank, paper_id in enumerate(PAPER_IDS, start=1)
    ]
    return SeedInitializationResult.model_construct(
        seed_arxiv_id="1706.03762",
        category="cs.LG",
        paper_count=5,
        preferences=Preferences.model_construct(
            topics=["cs.lg"], followed_authors=[], model_version=1, updated_at=ANCHOR
        ),
        digest=Digest.model_construct(
            id=UUID(int=99),
            digest_type=DigestType.MANUAL,
            generated_at=ANCHOR,
            entries=entries,
        ),
    )


class FakeSeedClient:
    def __init__(self, *, duplicates: bool = False) -> None:
        self.calls: list[str] = []
        self.events: list[UserEvent] = []
        self.duplicates = duplicates
        self.closed = False

    async def initialize(self, arxiv_reference: str) -> SeedInitializationResult:
        self.calls.append(f"initialize:{arxiv_reference}")
        return _initialization()

    async def get_paper(self, paper_id: UUID) -> Paper:
        self.calls.append(f"paper:{paper_id}")
        return Paper.model_construct(id=paper_id, processing_status=ProcessingStatus.READY)

    async def replace_preferences(self, update: PreferenceUpdate) -> Preferences:
        self.calls.append("preferences")
        return Preferences.model_construct(
            topics=update.topics,
            followed_authors=update.followed_authors,
            model_version=2,
            updated_at=ANCHOR,
        )

    async def ingest_events(self, events: list[UserEvent]) -> EventIngestionResult:
        self.calls.append("events")
        self.events = events
        count = len(events)
        return EventIngestionResult(
            accepted=0 if self.duplicates else count,
            duplicates=count if self.duplicates else 0,
        )

    async def aclose(self) -> None:
        self.closed = True


async def _bootstrap(_settings: Settings, display_name: str) -> DemoUserBootstrapResult:
    assert display_name == "Mneme Demo Researcher"
    return DemoUserBootstrapResult(
        user_id=USER_ID,
        user_created=True,
        preferences_created=True,
    )


async def _verify_state(
    settings: Settings,
    manifest: DemoSeedManifest,
    events: list[UserEvent],
) -> UUID:
    assert settings.demo_user_id == USER_ID
    content_sha256 = manifest.content_sha256()
    assert all(event.context["manifest_sha256"] == content_sha256 for event in events)
    return SEED_PAPER_ID


@pytest.mark.base
def test_seed_demo_waits_for_ready_and_replays_stable_events(tmp_path: Path) -> None:
    manifest = load_default_demo_seed_manifest()
    config = DemoSeedConfig(lock_file=tmp_path / "seed.lock")
    first_client = FakeSeedClient()

    first = asyncio.run(
        seed_demo(
            _settings(),
            manifest,
            config,
            token="demo-secret",
            client=first_client,
            bootstrapper=_bootstrap,
            state_verifier=_verify_state,
        )
    )

    assert first.paper_count == 5
    assert first.ready_papers == 5
    assert first.partial_papers == 0
    assert first.events_accepted == len(manifest.events)
    assert first.events_duplicates == 0
    assert first.seed_paper_id == str(SEED_PAPER_ID)
    assert first.digest_paper_ids == tuple(str(paper_id) for paper_id in PAPER_IDS)
    assert first.digest_arxiv_ids == tuple(f"2401.{rank:05d}" for rank in range(1, 6))
    assert first_client.closed
    assert first_client.calls[0] == "initialize:1706.03762"
    assert first_client.calls[-2:] == ["preferences", "events"]
    assert all(call.startswith("paper:") for call in first_client.calls[1:-2])
    assert [event.event_id for event in first_client.events] == [
        manifest.event_id(template) for template in manifest.events
    ]
    assert [event.occurred_at for event in first_client.events] == [
        manifest.event_time(template, ANCHOR) for template in manifest.events
    ]

    resumed_client = FakeSeedClient(duplicates=True)
    resumed = asyncio.run(
        seed_demo(
            _settings(),
            manifest,
            config,
            token="demo-secret",
            client=resumed_client,
            bootstrapper=_bootstrap,
            state_verifier=_verify_state,
        )
    )
    assert resumed.events_accepted == 0
    assert resumed.events_duplicates == len(manifest.events)
    assert [event.event_id for event in resumed_client.events] == [
        event.event_id for event in first_client.events
    ]


@pytest.mark.base
def test_seed_demo_accepts_permanent_partial_candidate(tmp_path: Path) -> None:
    partial_paper_id = PAPER_IDS[-1]

    class PartialSeedClient(FakeSeedClient):
        async def get_paper(self, paper_id: UUID) -> Paper:
            self.calls.append(f"paper:{paper_id}")
            processing_status = (
                ProcessingStatus.PARTIAL if paper_id == partial_paper_id else ProcessingStatus.READY
            )
            return Paper.model_construct(id=paper_id, processing_status=processing_status)

    result = asyncio.run(
        seed_demo(
            _settings(),
            load_default_demo_seed_manifest(),
            DemoSeedConfig(lock_file=tmp_path / "seed.lock"),
            token="demo-secret",
            client=PartialSeedClient(),
            bootstrapper=_bootstrap,
            state_verifier=_verify_state,
        )
    )

    assert result.paper_count == 5
    assert result.ready_papers == 4
    assert result.partial_papers == 1


@pytest.mark.base
def test_seed_demo_closes_client_after_remote_failure(tmp_path: Path) -> None:
    class FailingClient(FakeSeedClient):
        async def get_paper(self, paper_id: UUID) -> Paper:
            del paper_id
            raise DemoSeedError("https://secret.example")

    client = FailingClient()
    with pytest.raises(DemoSeedError):
        asyncio.run(
            seed_demo(
                _settings(),
                load_default_demo_seed_manifest(),
                DemoSeedConfig(lock_file=tmp_path / "seed.lock"),
                token="demo-secret",
                client=client,
                bootstrapper=_bootstrap,
                state_verifier=_verify_state,
            )
        )
    assert client.closed


@pytest.mark.base
def test_seed_demo_rejects_non_contiguous_digest_ranks(tmp_path: Path) -> None:
    class InvalidDigestClient(FakeSeedClient):
        async def initialize(self, arxiv_reference: str) -> SeedInitializationResult:
            result = await super().initialize(arxiv_reference)
            result.digest.entries[-1].rank = 4
            return result

    verifier_called = False

    async def unexpected_verifier(*_args: object) -> UUID:
        nonlocal verifier_called
        verifier_called = True
        return SEED_PAPER_ID

    with pytest.raises(DemoSeedError, match="incomplete digest"):
        asyncio.run(
            seed_demo(
                _settings(),
                load_default_demo_seed_manifest(),
                DemoSeedConfig(lock_file=tmp_path / "seed.lock"),
                token="demo-secret",
                client=InvalidDigestClient(),
                bootstrapper=_bootstrap,
                state_verifier=unexpected_verifier,
            )
        )
    assert not verifier_called


@pytest.mark.base
def test_demo_seed_lock_rejects_overlap(tmp_path: Path) -> None:
    async def exercise() -> None:
        lock_file = tmp_path / "seed.lock"
        async with demo_seed_lock(lock_file):
            with pytest.raises(DemoSeedError):
                async with demo_seed_lock(lock_file):
                    pass

    asyncio.run(exercise())


@pytest.mark.base
def test_private_demo_token_must_match_configured_digest(tmp_path: Path) -> None:
    token_file = tmp_path / "demo.token"
    token_file.write_text("demo-secret\n", encoding="ascii")
    token_file.chmod(0o600)

    assert read_private_demo_token(token_file, _settings()) == "demo-secret"

    with pytest.raises(DemoSeedConfigurationError):
        read_private_demo_token(token_file, _settings("different"))
    token_file.chmod(0o644)
    with pytest.raises(DemoSeedConfigurationError):
        read_private_demo_token(token_file, _settings())


@pytest.mark.base
@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "https://api.example.com"},
        {"lock_file": Path("relative")},
        {"request_timeout_seconds": 29},
        {"ready_timeout_seconds": 1801},
        {"poll_interval_seconds": 31},
    ],
)
def test_demo_seed_config_rejects_unsafe_values(overrides: dict[str, object]) -> None:
    with pytest.raises(DemoSeedConfigurationError):
        DemoSeedConfig(**overrides)  # type: ignore[arg-type]
