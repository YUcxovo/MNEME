"""Frozen v0.1 explicit-preference schemas and normalization."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Topic = Annotated[str, StringConstraints(min_length=1, max_length=100)]
FollowedAuthor = Annotated[str, StringConstraints(min_length=1, max_length=200)]


def normalize_preference_values(value: Any) -> Any:
    """Trim, Unicode-casefold, and stably deduplicate one preference list."""
    if not isinstance(value, list):
        return value
    if len(value) > 100:
        raise ValueError("preference lists may contain at most 100 entries")

    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("preference entries must be strings")
        candidate = item.strip().casefold()
        if not candidate:
            raise ValueError("preference entries must not be empty")
        if candidate not in seen:
            seen.add(candidate)
            normalized.append(candidate)
    return normalized


class Preferences(BaseModel):
    """Stored preferences returned for the authenticated demo user."""

    topics: list[Topic] = Field(max_length=100, json_schema_extra={"uniqueItems": True})
    followed_authors: list[FollowedAuthor] = Field(
        max_length=100, json_schema_extra={"uniqueItems": True}
    )
    model_version: int
    updated_at: datetime | None = None


class PreferenceUpdate(BaseModel):
    """Complete replacement of both explicit preference lists."""

    model_config = ConfigDict(extra="forbid")

    topics: list[Topic] = Field(max_length=100, json_schema_extra={"uniqueItems": True})
    followed_authors: list[FollowedAuthor] = Field(
        max_length=100, json_schema_extra={"uniqueItems": True}
    )

    _normalize_topics = field_validator("topics", mode="before")(normalize_preference_values)
    _normalize_authors = field_validator("followed_authors", mode="before")(
        normalize_preference_values
    )
