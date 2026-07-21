"""ARQ worker entry point and shared worker configuration."""

from typing import Any, ClassVar

import structlog
from arq import cron

from mneme.ai.budget import BudgetGuard
from mneme.ai.embeddings import EmbeddingService, OpenAIEmbeddingProvider
from mneme.ai.service import build_llm_service
from mneme.ai.summarization import SummarizationService
from mneme.core.config import Settings, get_settings
from mneme.core.logging import configure_logging
from mneme.db.session import Database
from mneme.redis.arq import create_arq_redis_settings
from mneme.redis.client import create_redis_client
from mneme.services.documents import DocumentStorage, PdfDownloader, PdfParser
from mneme.tasks.ai_jobs import chunk_paper, embed_chunks, summarize_paper
from mneme.tasks.digest_jobs import assemble_digest
from mneme.tasks.dispatch_recovery import recover_revision_dispatches
from mneme.tasks.document_jobs import download_pdf, parse_pdf
from mneme.tasks.metadata_jobs import fetch_metadata

logger = structlog.get_logger(__name__)


async def worker_probe(_: dict[str, Any]) -> str:
    """Return a deterministic result for worker smoke tests."""
    return "ok"


async def on_startup(context: dict[str, Any]) -> None:
    """Configure the standalone worker process and shared context."""
    settings = get_settings()
    configure_logging(settings)
    context["settings"] = settings
    context["database"] = Database(settings.database_url, echo=settings.debug)
    context["document_storage"] = DocumentStorage(settings.paper_storage_dir)
    context["pdf_downloader"] = PdfDownloader(
        user_agent=settings.arxiv_user_agent,
        request_interval_seconds=settings.arxiv_request_interval_seconds,
        timeout_seconds=settings.pdf_download_timeout_seconds,
        max_attempts=settings.pdf_download_max_attempts,
        max_bytes=settings.pdf_max_bytes,
    )
    context["pdf_parser"] = PdfParser(min_text_chars=settings.pdf_min_text_chars)
    redis_client = create_redis_client(settings)
    context["shared_redis"] = redis_client
    llm_service = build_llm_service(settings, redis_client)
    context["summarizer"] = SummarizationService(
        llm_service,
        max_input_chars=settings.ai_summary_max_input_chars,
        max_output_tokens=settings.ai_summary_max_output_tokens,
    )
    if settings.openai_api_key is not None:
        context["embedder"] = EmbeddingService(
            provider=OpenAIEmbeddingProvider(
                api_key=settings.openai_api_key.get_secret_value(),
                timeout_seconds=settings.llm_timeout_seconds,
            ),
            budget=BudgetGuard(redis_client, daily_cap_usd=settings.ai_daily_budget_usd),
            model=settings.ai_embedding_model,
            batch_size=settings.ai_embedding_batch_size,
        )
    else:
        context["embedder"] = None
    logger.info("worker_started", queue=settings.arq_queue_name)


async def on_shutdown(context: dict[str, Any]) -> None:
    """Record a clean worker shutdown."""
    settings: Settings = context.get("settings", get_settings())
    database: Database | None = context.get("database")
    pdf_downloader: PdfDownloader | None = context.get("pdf_downloader")
    if pdf_downloader is not None:
        await pdf_downloader.aclose()
    if database is not None:
        await database.dispose()
    shared_redis = context.get("shared_redis")
    if shared_redis is not None:
        await shared_redis.aclose()
    logger.info("worker_stopped", queue=settings.arq_queue_name)


_settings = get_settings()


class WorkerSettings:
    """Configuration loaded by the ARQ command-line worker."""

    functions: ClassVar = [
        worker_probe,
        fetch_metadata,
        download_pdf,
        parse_pdf,
        summarize_paper,
        chunk_paper,
        embed_chunks,
        assemble_digest,
    ]
    cron_jobs: ClassVar = [
        cron(recover_revision_dispatches, second=15, run_at_startup=True),
    ]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = create_arq_redis_settings(_settings)
    queue_name = _settings.arq_queue_name
    max_jobs = _settings.arq_max_jobs
    job_timeout = _settings.arq_job_timeout_seconds
    max_tries = _settings.arq_max_tries
    health_check_interval = _settings.arq_health_check_interval_seconds
    health_check_key = "mneme:worker:health"
