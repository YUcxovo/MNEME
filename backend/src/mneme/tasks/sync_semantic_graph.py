"""Cron-friendly CLI for one paper's Semantic Scholar citation graph."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from uuid import UUID

from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.repositories.citation_graph import (
    CitationIdentityConflict,
    CitationPersistenceResult,
)
from mneme.services.semantic_scholar import (
    SemanticScholarClient,
    SemanticScholarClientError,
)
from mneme.services.semantic_scholar.sync import (
    SemanticGraphSyncService,
    SemanticGraphSyncSummary,
    SemanticGraphTargetNotFound,
)


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit single-paper synchronization command."""
    parser = argparse.ArgumentParser(
        description="Synchronize one local paper's Semantic Scholar citation graph."
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--paper-id", type=UUID, help="internal paper UUID")
    target.add_argument("--arxiv-id", help="unversioned local arXiv work ID")
    parser.add_argument(
        "--limit",
        type=int,
        help="maximum neighbors fetched in each direction (defaults to configuration)",
    )
    return parser


async def run(
    *,
    settings: Settings | None = None,
    paper_id: UUID | None = None,
    arxiv_id: str | None = None,
    limit: int | None = None,
) -> SemanticGraphSyncSummary:
    """Synchronize one paper and release HTTP/database resources."""
    resolved_settings = settings or get_settings()
    resolved_limit = (
        limit if limit is not None else resolved_settings.semantic_scholar_max_neighbors
    )
    if not 1 <= resolved_limit <= resolved_settings.semantic_scholar_max_neighbors:
        raise ValueError("limit exceeds the configured Semantic Scholar maximum")

    database = Database.from_settings(resolved_settings)
    try:
        async with SemanticScholarClient(resolved_settings) as client:
            service = SemanticGraphSyncService(database.session_factory, client)
            return await service.sync(
                paper_id=paper_id,
                arxiv_id=arxiv_id,
                limit=resolved_limit,
            )
    finally:
        await database.dispose()


def _direction_payload(persistence: CitationPersistenceResult) -> dict[str, int]:
    return {
        "duplicates": persistence.duplicates,
        "inserted": persistence.inserted,
        "observed": persistence.observed,
        "resolved": persistence.resolved,
        "skipped_self": persistence.skipped_self,
    }


def main() -> None:
    """Run graph synchronization with safe JSON output and exit statuses."""
    arguments = build_parser().parse_args()
    try:
        summary = asyncio.run(
            run(
                paper_id=arguments.paper_id,
                arxiv_id=arguments.arxiv_id,
                limit=arguments.limit,
            )
        )
    except (SemanticGraphTargetNotFound, ValueError) as error:
        print(
            json.dumps(
                {"error": "semantic_graph_target_invalid", "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(2) from None
    except CitationIdentityConflict as error:
        print(
            json.dumps(
                {"error": "semantic_graph_identity_conflict", "message": str(error)},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(3) from None
    except SemanticScholarClientError:
        print(
            json.dumps(
                {
                    "error": "semantic_graph_upstream_unavailable",
                    "message": "Semantic Scholar graph synchronization failed.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None
    except Exception:
        print(
            json.dumps(
                {
                    "error": "semantic_graph_unavailable",
                    "message": "Graph synchronization failed unexpectedly.",
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            {
                "arxiv_id": summary.arxiv_id,
                "citations": _direction_payload(summary.citations),
                "paper_id": str(summary.paper_id),
                "references": _direction_payload(summary.references),
                "semantic_scholar_id": summary.semantic_scholar_id,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
