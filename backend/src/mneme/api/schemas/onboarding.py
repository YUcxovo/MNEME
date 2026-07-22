"""Local-demo seed-paper initialization schemas."""

from pydantic import BaseModel, Field

from mneme.api.schemas.digests import Digest
from mneme.api.schemas.preferences import Preferences


class SeedInitializationRequest(BaseModel):
    """One arXiv URL or identifier supplied during first-run setup."""

    arxiv_reference: str = Field(min_length=1, max_length=300)


class SeedInitializationResult(BaseModel):
    """Completed five-paper library returned only after backend preparation."""

    seed_arxiv_id: str
    category: str
    paper_count: int
    preferences: Preferences
    digest: Digest
