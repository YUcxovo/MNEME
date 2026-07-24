"""Run the RAG-graded QA evaluation against ingested papers.

Usage: ``uv run python -m mneme.cli.run_qa_eval [--fixtures PATH] [--output PATH]``

Requires a running PostgreSQL/Redis with the fixture papers already ingested,
parsed, and embedded, plus a configured LLM provider. Fixtures whose paper is
missing or not yet embedded are reported as skipped, never silently dropped:
a run that skips cases prints them to stderr and records them in the output.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.embeddings import build_embedding_service
from mneme.ai.evaluation import (
    QAFixture,
    RagCaseOutcome,
    RagEvaluationHarness,
    load_qa_fixtures,
)
from mneme.ai.qa import REFUSAL_ANSWER, GroundedAnswerService
from mneme.ai.retrieval import RetrievalService
from mneme.ai.service import build_llm_service
from mneme.core.config import Settings, get_settings
from mneme.db.session import Database
from mneme.models.artifact import PaperChunk
from mneme.models.paper import Paper, PaperVersion
from mneme.redis.client import create_redis_client
from mneme.repositories.artifacts import ArtifactRepository

DEFAULT_FIXTURES = (
    Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "eval" / "qa_seed_v2.json"
)


def build_parser() -> argparse.ArgumentParser:
    """Build the evaluation command parser."""
    parser = argparse.ArgumentParser(
        description="Grade the retrieval + grounded-QA pipeline over a fixture set."
    )
    parser.add_argument(
        "--fixtures",
        type=Path,
        default=DEFAULT_FIXTURES,
        help="path to a QA fixture JSON file (default: qa_seed_v2.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write the full JSON report here in addition to stdout",
    )
    return parser


async def _resolve_runnable(
    session: AsyncSession, artifacts: ArtifactRepository, fixture: QAFixture
) -> tuple[Paper, PaperVersion] | str:
    """Return the fixture's paper and version, or a skip reason."""
    paper = (
        await session.execute(select(Paper).where(Paper.arxiv_id == fixture.arxiv_id))
    ).scalar_one_or_none()
    if paper is None:
        return "paper_not_ingested"
    version = await artifacts.get_latest_version(paper.id)
    if version is None:
        return "paper_not_ingested"
    has_embedded_chunk = (
        await session.execute(
            select(
                exists().where(
                    PaperChunk.paper_version_id == version.id,
                    PaperChunk.embedding.is_not(None),
                )
            )
        )
    ).scalar_one()
    if not has_embedded_chunk:
        return "paper_not_embedded"
    return paper, version


async def run(settings: Settings, *, fixtures_path: Path) -> dict[str, object]:
    """Evaluate every runnable fixture and report metrics plus skips."""
    fixture_file = load_qa_fixtures(fixtures_path)
    database = Database(settings.database_url, echo=False)
    redis = create_redis_client(settings)
    evaluated = 0
    skipped: list[dict[str, str]] = []
    report = None
    try:
        llm = build_llm_service(settings, redis)
        embedder = build_embedding_service(settings, redis)
        if embedder is None:
            raise SystemExit("No embedding provider configured; cannot run retrieval.")

        async with database.session_factory() as session:
            artifacts = ArtifactRepository(session)
            retrieval = RetrievalService(
                embedder=embedder, artifacts=artifacts, top_k=settings.ai_retrieval_top_k
            )
            generator = GroundedAnswerService(
                llm,
                rerank_top_n=settings.ai_qa_rerank_top_n,
                min_evidence_score=settings.ai_qa_min_evidence_score,
                max_output_tokens=settings.ai_qa_max_output_tokens,
            )

            runnable: dict[str, tuple[QAFixture, Paper, PaperVersion]] = {}
            for fixture in fixture_file.fixtures:
                resolved = await _resolve_runnable(session, artifacts, fixture)
                if isinstance(resolved, str):
                    skipped.append({"fixture_id": fixture.fixture_id, "reason": resolved})
                    continue
                runnable[fixture.fixture_id] = (fixture, *resolved)

            async def answer(fixture: QAFixture) -> RagCaseOutcome:
                _, paper, version = runnable[fixture.fixture_id]
                chunks = await retrieval.retrieve(
                    paper_id=paper.id, paper_version_id=version.id, question=fixture.question
                )
                grounded = await generator.answer(question=fixture.question, chunks=chunks)
                return RagCaseOutcome(
                    answer=grounded.answer,
                    refused=grounded.answer == REFUSAL_ANSWER,
                    retrieved_sections=tuple(
                        chunk.section_title for chunk in chunks if chunk.section_title
                    ),
                    source_match_status=grounded.source_match_status,
                    verified_citations=len(grounded.citations),
                    completion=grounded.completion,
                )

            if runnable:
                evaluated = len(runnable)
                report = await RagEvaluationHarness(answer).run(
                    tuple(entry[0] for entry in runnable.values()),
                    fixture_version=fixture_file.fixture_version,
                )
    finally:
        await redis.aclose()
        await database.dispose()

    return {
        "fixture_version": fixture_file.fixture_version,
        "evaluated": evaluated,
        "skipped": skipped,
        "report": json.loads(report.model_dump_json()) if report is not None else None,
    }


def main() -> None:
    """Run the evaluation and emit a JSON report."""
    arguments = build_parser().parse_args()
    payload = asyncio.run(run(get_settings(), fixtures_path=arguments.fixtures))
    skips = payload["skipped"]
    assert isinstance(skips, list)
    for skip in skips:
        print(f"skipped {skip['fixture_id']}: {skip['reason']}", file=sys.stderr)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if arguments.output is not None:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
