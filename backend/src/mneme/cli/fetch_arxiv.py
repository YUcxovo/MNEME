"""Fetch and persist one page of arXiv metadata without running migrations."""

import argparse
import asyncio
import json
from dataclasses import asdict

from mneme.core.config import get_settings
from mneme.db.session import Database
from mneme.services.arxiv.client import ArxivClient
from mneme.services.arxiv.ingestion import ArxivIngestionService, ArxivIngestionSummary


def build_parser() -> argparse.ArgumentParser:
    """Build the standalone metadata-ingestion command parser."""
    parser = argparse.ArgumentParser(
        description="Fetch and persist one arXiv category page as metadata_only records."
    )
    parser.add_argument("category", help="arXiv category such as cs.AI")
    parser.add_argument("--start", type=int, default=0, help="zero-based result offset")
    parser.add_argument("--max-results", type=int, default=20, help="page size")
    return parser


async def run(category: str, *, start: int, max_results: int) -> ArxivIngestionSummary:
    """Run one ingestion page using configured HTTP and database resources."""
    settings = get_settings()
    database = Database(settings.database_url, echo=settings.debug)
    try:
        async with (
            ArxivClient(settings) as client,
            database.session_factory() as session,
        ):
            service = ArxivIngestionService(client, session)
            return await service.ingest_category(
                category,
                start=start,
                max_results=max_results,
            )
    finally:
        await database.dispose()


def main() -> None:
    """Parse arguments, ingest one page, and print machine-readable counts."""
    arguments = build_parser().parse_args()
    summary = asyncio.run(
        run(
            arguments.category,
            start=arguments.start,
            max_results=arguments.max_results,
        )
    )
    print(json.dumps(asdict(summary), sort_keys=True))


if __name__ == "__main__":
    main()
