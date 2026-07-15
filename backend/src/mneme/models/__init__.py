"""SQLAlchemy model package and metadata registration."""

from mneme.models.artifact import PaperChunk, PaperSummary, SourceMatchStatus, SummaryStatus
from mneme.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from mneme.models.digest import Digest, DigestEntry, DigestType
from mneme.models.graph import Citation
from mneme.models.paper import Author, Paper, PaperAuthor, PaperVersion, ProcessingStatus
from mneme.models.user import EMBEDDING_DIMENSIONS, User, UserEvent, UserEventType, UserPreference

__all__ = [
    "EMBEDDING_DIMENSIONS",
    "Author",
    "Base",
    "Citation",
    "Digest",
    "DigestEntry",
    "DigestType",
    "Paper",
    "PaperAuthor",
    "PaperChunk",
    "PaperSummary",
    "PaperVersion",
    "ProcessingStatus",
    "SourceMatchStatus",
    "SummaryStatus",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserEvent",
    "UserEventType",
    "UserPreference",
]
