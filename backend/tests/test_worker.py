"""Tests for the minimal ARQ worker scaffold."""

import asyncio

import pytest

from mneme.core.config import Settings
from mneme.redis.arq import create_arq_redis_settings
from mneme.tasks.worker import WorkerSettings, worker_probe


@pytest.mark.base
@pytest.mark.pipeline
def test_arq_settings_reuse_application_redis_config() -> None:
    settings = Settings(
        redis_url="rediss://worker:secret@queue:6380/3",
        redis_max_connections=8,
        redis_socket_timeout_seconds=4,
        _env_file=None,
    )

    redis_settings = create_arq_redis_settings(settings)

    assert redis_settings.host == "queue"
    assert redis_settings.port == 6380
    assert redis_settings.database == 3
    assert redis_settings.username == "worker"
    assert redis_settings.password == "secret"
    assert redis_settings.ssl is True
    assert redis_settings.conn_timeout == 4
    assert redis_settings.max_connections == 8


@pytest.mark.base
@pytest.mark.pipeline
def test_worker_registers_probe_and_ai_stages() -> None:
    from mneme.tasks.ai_jobs import chunk_paper, embed_chunks, summarize_paper
    from mneme.tasks.document_jobs import download_pdf, parse_pdf
    from mneme.tasks.metadata_jobs import fetch_metadata

    assert WorkerSettings.functions == [
        worker_probe,
        fetch_metadata,
        download_pdf,
        parse_pdf,
        summarize_paper,
        chunk_paper,
        embed_chunks,
    ]
    assert WorkerSettings.queue_name == "mneme:jobs"
    assert WorkerSettings.health_check_key == "mneme:worker:health"
    assert asyncio.run(worker_probe({})) == "ok"
