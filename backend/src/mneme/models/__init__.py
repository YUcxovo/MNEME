"""SQLAlchemy model package and metadata registration."""

from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from mneme.models.user import EMBEDDING_DIMENSIONS, User, UserEvent, UserEventType, UserPreference

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserEvent",
    "UserEventType",
    "UserPreference",
]
