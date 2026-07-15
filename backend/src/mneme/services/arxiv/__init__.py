"""arXiv metadata ingestion primitives."""

from mneme.services.arxiv.client import ArxivClient, ArxivClientError, ArxivHTTPError
from mneme.services.arxiv.parser import ArxivAPIError, ArxivParseError, parse_arxiv_feed
from mneme.services.arxiv.types import ArxivAuthorRecord, ArxivFeed, ArxivPaperRecord

__all__ = [
    "ArxivAPIError",
    "ArxivAuthorRecord",
    "ArxivClient",
    "ArxivClientError",
    "ArxivFeed",
    "ArxivHTTPError",
    "ArxivPaperRecord",
    "ArxivParseError",
    "parse_arxiv_feed",
]
