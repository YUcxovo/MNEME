"""Strict versioned input contract for installation-local demo replay."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from importlib import resources
from pathlib import Path
from typing import Annotated, Literal, Self
from uuid import UUID, uuid5

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from mneme.api.routes.onboarding_support import normalize_arxiv_reference
from mneme.api.schemas.preferences import normalize_preference_values
from mneme.models.user import UserEventType

DEMO_EVENT_NAMESPACE = UUID("ec66ded0-0b4c-4f03-a719-6cbd4bd88aad")
ManifestId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{2,63}$")]


class DemoManifestError(ValueError):
    """A demo seed manifest is unreadable or violates the frozen schema."""


class DemoEventTemplate(BaseModel):
    """One deterministic synthetic interaction relative to the digest anchor."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: ManifestId
    paper_rank: int = Field(ge=1, le=5)
    event_type: UserEventType
    seconds_before_anchor: int = Field(ge=0, le=7 * 24 * 3600)
    duration_ms: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_duration_scope(self) -> Self:
        """Match the public behavioral-event duration contract."""
        if self.event_type is UserEventType.DIGEST_DISMISSED:
            raise ValueError("demo events must be paper scoped")
        if self.event_type is UserEventType.PAPER_OPENED:
            if self.duration_ms is None:
                raise ValueError("paper_opened demo events require duration_ms")
        elif self.duration_ms is not None:
            raise ValueError("duration_ms is only valid for paper_opened")
        return self


class DemoSeedManifest(BaseModel):
    """Frozen, provider-independent demo seed inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["demo-seed-manifest-v1"]
    manifest_id: ManifestId
    seed_arxiv_reference: str = Field(min_length=1, max_length=300)
    display_name: str = Field(min_length=1, max_length=200)
    onboarding_limit: Literal[5]
    topics: list[str] = Field(min_length=1, max_length=100)
    followed_authors: list[str] = Field(max_length=100)
    events: tuple[DemoEventTemplate, ...] = Field(min_length=1, max_length=50)

    _normalize_topics = field_validator("topics", mode="before")(normalize_preference_values)
    _normalize_authors = field_validator("followed_authors", mode="before")(
        normalize_preference_values
    )

    @field_validator("seed_arxiv_reference")
    @classmethod
    def normalize_seed_reference(cls, value: str) -> str:
        """Persist the canonical unversioned arXiv identifier."""
        return normalize_arxiv_reference(value)

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str) -> str:
        """Reject invisible or multiline demo identity values."""
        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("display_name must not be empty")
        return normalized

    @model_validator(mode="after")
    def validate_event_sequence(self) -> Self:
        """Require stable keys, valid ranks, and exposure-gated negative evidence."""
        if len({event.key for event in self.events}) != len(self.events):
            raise ValueError("demo event keys must be unique")
        if any(event.paper_rank > self.onboarding_limit for event in self.events):
            raise ValueError("demo event rank exceeds onboarding result size")
        event_types = {event.event_type for event in self.events}
        if UserEventType.PAPER_SKIPPED not in event_types:
            raise ValueError("demo events require one bounded negative signal")
        if not event_types.intersection({UserEventType.PAPER_SAVED, UserEventType.QUESTION_ASKED}):
            raise ValueError("demo events require one explicit positive signal")
        impressions = [
            event for event in self.events if event.event_type is UserEventType.PAPER_IMPRESSION
        ]
        for skipped in (
            event for event in self.events if event.event_type is UserEventType.PAPER_SKIPPED
        ):
            if not any(
                impression.paper_rank == skipped.paper_rank
                and 0
                < impression.seconds_before_anchor - skipped.seconds_before_anchor
                <= 7 * 24 * 3600
                for impression in impressions
            ):
                raise ValueError("paper_skipped requires a preceding bounded impression")
        return self

    def event_id(self, event: DemoEventTemplate) -> UUID:
        """Return a stable idempotency identity for one manifest event."""
        return uuid5(DEMO_EVENT_NAMESPACE, f"{self.manifest_id}:{event.key}")

    def event_time(self, event: DemoEventTemplate, anchor: datetime) -> datetime:
        """Resolve one event timestamp from a persisted timezone-aware digest anchor."""
        if anchor.tzinfo is None or anchor.utcoffset() is None:
            raise DemoManifestError("demo event anchor must include a timezone")
        return anchor - timedelta(seconds=event.seconds_before_anchor)

    def content_sha256(self) -> str:
        """Hash canonical validated inputs for audit and resume checks."""
        raw = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()


def parse_demo_seed_manifest(raw: str | bytes) -> DemoSeedManifest:
    """Parse strict JSON while presenting one bounded domain error."""
    try:
        return DemoSeedManifest.model_validate_json(raw)
    except (ValueError, TypeError) as exception:
        raise DemoManifestError("Demo seed manifest is invalid") from exception


def load_demo_seed_manifest(path: Path) -> DemoSeedManifest:
    """Load a regular, non-symlink manifest file."""
    if path.is_symlink() or not path.is_file():
        raise DemoManifestError("Demo seed manifest is unavailable")
    try:
        return parse_demo_seed_manifest(path.read_bytes())
    except OSError as exception:
        raise DemoManifestError("Demo seed manifest is unavailable") from exception


def load_default_demo_seed_manifest() -> DemoSeedManifest:
    """Load the packaged live-core manifest."""
    raw = resources.files("mneme.demo.manifests").joinpath("demo-seed-v1.json").read_bytes()
    return parse_demo_seed_manifest(raw)
