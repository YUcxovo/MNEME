"""Run the RAG-graded QA evaluation against ingested papers.

Usage: ``uv run python -m mneme.cli.run_qa_eval [--fixtures PATH] [--output PATH]``

Requires a running PostgreSQL/Redis with the fixture papers already ingested,
parsed, and embedded, plus a configured LLM provider. Each fixture pins an
exact arXiv revision (``arxiv_version``); a case runs only when that exact
revision is present with a complete embedding set produced by the configured
embedding model. Anything else is reported as skipped with the reason and
counts, never silently dropped, and a run that evaluates zero fixtures exits
nonzero so automation cannot mistake an empty run for a healthy one.

Completions from this CLI hit the shared LLM cache but are not persisted to
``qa_messages``; the JSON report (including its ``run_config`` provenance
block) is the only durable output of a run.
"""

import argparse
import asyncio
import json
import sys
import time
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from mneme.ai.embeddings import build_embedding_service
from mneme.ai.evaluation import (
    QAFixture,
    RagCaseOutcome,
    RagEvaluationHarness,
    RagRunConfig,
    load_qa_fixtures,
)
from mneme.ai.prompts import QA_PROMPT_VERSION
from mneme.ai.qa import REFUSAL_ANSWER, GroundedAnswerService
from mneme.ai.retrieval import DEFAULT_CONTEXT_ANCHOR_COUNT, RetrievalService
from mneme.ai.routing import infer_provider
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

EXIT_NO_CASES_EVALUATED = 2


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


def build_run_config(settings: Settings, *, embedding_model: str) -> RagRunConfig:
    """Snapshot every setting that shapes a run's metrics, for the report."""
    return RagRunConfig(
        llm_provider=infer_provider(settings.llm_qa_model).value,
        llm_model=settings.llm_qa_model,
        prompt_version=QA_PROMPT_VERSION,
        embedding_backend=settings.ai_embedding_backend.value,
        embedding_model=embedding_model,
        retrieval_top_k=settings.ai_retrieval_top_k,
        context_anchor_count=DEFAULT_CONTEXT_ANCHOR_COUNT,
        rerank_top_n=settings.ai_qa_rerank_top_n,
        min_evidence_score=settings.ai_qa_min_evidence_score,
        max_output_tokens=settings.ai_qa_max_output_tokens,
        cache_enabled=settings.ai_cache_enabled,
        qa_cache_ttl_seconds=settings.ai_qa_cache_ttl_seconds,
    )


async def resolve_runnable(
    session: AsyncSession, fixture: QAFixture, *, embedding_model: str
) -> tuple[Paper, PaperVersion] | dict[str, str]:
    """Return the fixture's pinned paper revision, or a skip record.

    A fixture is runnable only when its exact pinned ``arxiv_version`` row
    exists and every chunk of that revision carries an embedding produced by
    the configured embedding model. Partial embedding sets and model
    mismatches are skips with explicit counts, not silent degradation.
    """

    def skip(reason: str, detail: str) -> dict[str, str]:
        return {"fixture_id": fixture.fixture_id, "reason": reason, "detail": detail}

    if fixture.arxiv_version is None:
        return skip(
            "fixture_not_version_pinned",
            f"{fixture.arxiv_id} has no arxiv_version pin; live runs require one",
        )
    paper = (
        await session.execute(select(Paper).where(Paper.arxiv_id == fixture.arxiv_id))
    ).scalar_one_or_none()
    if paper is None:
        return skip("paper_not_ingested", f"{fixture.arxiv_id} not found")
    version = (
        await session.execute(
            select(PaperVersion).where(
                PaperVersion.paper_id == paper.id,
                PaperVersion.version_number == fixture.arxiv_version,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        return skip(
            "pinned_version_not_ingested",
            f"{fixture.arxiv_id}v{fixture.arxiv_version} not found",
        )
    total_chunks = (
        await session.execute(
            select(func.count())
            .select_from(PaperChunk)
            .where(PaperChunk.paper_version_id == version.id)
        )
    ).scalar_one()
    ready_chunks = (
        await session.execute(
            select(func.count())
            .select_from(PaperChunk)
            .where(
                PaperChunk.paper_version_id == version.id,
                PaperChunk.embedding.is_not(None),
                PaperChunk.embedding_model == embedding_model,
            )
        )
    ).scalar_one()
    if total_chunks == 0 or ready_chunks != total_chunks:
        return skip(
            "embeddings_incomplete",
            f"{fixture.arxiv_id}v{fixture.arxiv_version}: {ready_chunks}/{total_chunks} "
            f"chunks embedded with {embedding_model!r}",
        )
    return paper, version


async def evaluate_case(
    fixture: QAFixture,
    *,
    paper: Paper,
    version: PaperVersion,
    retrieval: RetrievalService,
    generator: GroundedAnswerService,
    embedding_spend: list[Decimal],
) -> RagCaseOutcome:
    """Run one fixture through the live pipeline and split its telemetry.

    ``embedding_spend`` is the run-level accumulator fed by the embedding
    service's spend listener; cases run sequentially, so draining it here
    attributes each query-embedding cost to the case that incurred it.
    """
    embedding_spend.clear()
    started = time.monotonic()
    chunks = await retrieval.retrieve(
        paper_id=paper.id, paper_version_id=version.id, question=fixture.question
    )
    grounded = await generator.answer(question=fixture.question, chunks=chunks)
    pipeline_latency_ms = max(1, round((time.monotonic() - started) * 1000))
    return RagCaseOutcome(
        answer=grounded.answer,
        refused=grounded.answer == REFUSAL_ANSWER,
        dense_sections=tuple(
            chunk.section_title
            for chunk in chunks
            if chunk.section_title and not chunk.is_context_anchor
        ),
        anchor_sections=tuple(
            chunk.section_title
            for chunk in chunks
            if chunk.section_title and chunk.is_context_anchor
        ),
        source_match_status=grounded.source_match_status,
        verified_citations=len(grounded.citations),
        completion=grounded.completion,
        query_embedding_cost=sum(embedding_spend, start=Decimal(0)),
        pipeline_latency_ms=pipeline_latency_ms,
    )


async def run(settings: Settings, *, fixtures_path: Path) -> dict[str, object]:
    """Evaluate every runnable fixture and report metrics plus skips."""
    fixture_file = load_qa_fixtures(fixtures_path)
    database = Database(settings.database_url, echo=False)
    redis = create_redis_client(settings)
    evaluated = 0
    skipped: list[dict[str, str]] = []
    corpus: dict[str, dict[str, object]] = {}
    report = None
    embedding_spend: list[Decimal] = []
    try:
        llm = build_llm_service(settings, redis)
        embedder = build_embedding_service(settings, redis, spend_listener=embedding_spend.append)
        if embedder is None:
            raise SystemExit("No embedding provider configured; cannot run retrieval.")
        run_config = build_run_config(settings, embedding_model=embedder.model)

        async with database.session_factory() as session:
            retrieval = RetrievalService(
                embedder=embedder,
                artifacts=ArtifactRepository(session),
                top_k=settings.ai_retrieval_top_k,
                context_anchor_count=DEFAULT_CONTEXT_ANCHOR_COUNT,
            )
            generator = GroundedAnswerService(
                llm,
                rerank_top_n=settings.ai_qa_rerank_top_n,
                min_evidence_score=settings.ai_qa_min_evidence_score,
                max_output_tokens=settings.ai_qa_max_output_tokens,
            )

            runnable: dict[str, tuple[QAFixture, Paper, PaperVersion]] = {}
            for fixture in fixture_file.fixtures:
                resolved = await resolve_runnable(session, fixture, embedding_model=embedder.model)
                if isinstance(resolved, dict):
                    skipped.append(resolved)
                    continue
                paper, version = resolved
                runnable[fixture.fixture_id] = (fixture, paper, version)
                corpus[fixture.arxiv_id] = {
                    "arxiv_version": version.version_number,
                    "paper_version_id": str(version.id),
                }

            async def answer(fixture: QAFixture) -> RagCaseOutcome:
                _, paper, version = runnable[fixture.fixture_id]
                return await evaluate_case(
                    fixture,
                    paper=paper,
                    version=version,
                    retrieval=retrieval,
                    generator=generator,
                    embedding_spend=embedding_spend,
                )

            evaluated = len(runnable)
            if runnable:
                report = await RagEvaluationHarness(answer).run(
                    tuple(entry[0] for entry in runnable.values()),
                    fixture_version=fixture_file.fixture_version,
                    run_config=run_config,
                )
    finally:
        await redis.aclose()
        await database.dispose()

    return {
        "fixture_version": fixture_file.fixture_version,
        "evaluated": evaluated,
        "corpus": corpus,
        "skipped": skipped,
        "report": json.loads(report.model_dump_json()) if report is not None else None,
    }


def main() -> None:
    """Run the evaluation and emit a JSON report; exit nonzero on empty runs."""
    arguments = build_parser().parse_args()
    payload = asyncio.run(run(get_settings(), fixtures_path=arguments.fixtures))
    skips = payload["skipped"]
    assert isinstance(skips, list)
    for skip in skips:
        print(f"skipped {skip['fixture_id']}: {skip['reason']} ({skip['detail']})", file=sys.stderr)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    print(rendered)
    if arguments.output is not None:
        arguments.output.write_text(rendered + "\n", encoding="utf-8")
    if not payload["evaluated"]:
        print("error: no fixtures were evaluated; see skip reasons above", file=sys.stderr)
        raise SystemExit(EXIT_NO_CASES_EVALUATED)


if __name__ == "__main__":
    main()
