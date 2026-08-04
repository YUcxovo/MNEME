"""Tests for environment-backed settings."""

from pathlib import Path

import pytest

from mneme.core.config import EmbeddingBackend, Environment, Settings


@pytest.mark.base
def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8000
    assert settings.api_workers == 2
    assert settings.api_timeout_seconds == 120
    assert settings.api_graceful_timeout_seconds == 90
    assert settings.api_keepalive_seconds == 5
    assert settings.api_max_requests == 1000
    assert settings.api_max_requests_jitter == 100
    assert settings.readiness_timeout_seconds == 2
    assert settings.database_pool_size == 5
    assert settings.database_max_overflow == 5
    assert settings.database_pool_timeout_seconds == 30
    assert settings.database_pool_recycle_seconds == 1800
    assert str(settings.redis_url) == "redis://localhost:6379/0"
    assert settings.redis_max_connections == 10
    assert str(settings.arxiv_api_url) == "https://export.arxiv.org/api/query"
    assert settings.arxiv_request_interval_seconds == 3
    assert settings.arxiv_max_results == 100
    assert settings.daily_arxiv_categories == ("cs.AI", "cs.LG")
    assert settings.arxiv_daily_max_results == 20
    assert settings.semantic_scholar_request_interval_seconds == 1
    assert settings.semantic_scholar_batch_size <= 500
    assert settings.semantic_scholar_page_size <= 1000
    assert settings.paper_storage_dir == Path(".data/papers")
    assert settings.pdf_max_bytes == 50 * 1024 * 1024
    assert settings.pdf_download_timeout_seconds == 60
    assert settings.pdf_download_max_attempts == 3
    assert settings.pdf_min_text_chars == 500
    assert settings.demo_token_sha256 is None
    assert settings.demo_user_id is None
    assert settings.deepseek_api_key is None
    assert settings.deepseek_thinking_enabled is False
    assert settings.ai_embedding_backend is EmbeddingBackend.OPENAI
    assert settings.use_json_logs is False


@pytest.mark.base
def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MNEME_ENVIRONMENT", "testing")
    monkeypatch.setenv("MNEME_DEBUG", "true")
    monkeypatch.setenv("MNEME_LOG_LEVEL", "warning")
    monkeypatch.setenv("MNEME_API_PORT", "8080")
    monkeypatch.setenv("MNEME_API_WORKERS", "4")
    monkeypatch.setenv("MNEME_API_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("MNEME_API_GRACEFUL_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("MNEME_API_KEEPALIVE_SECONDS", "10")
    monkeypatch.setenv("MNEME_API_MAX_REQUESTS", "2000")
    monkeypatch.setenv("MNEME_API_MAX_REQUESTS_JITTER", "200")
    monkeypatch.setenv("MNEME_READINESS_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("MNEME_DATABASE_POOL_SIZE", "8")
    monkeypatch.setenv("MNEME_DATABASE_MAX_OVERFLOW", "3")
    monkeypatch.setenv("MNEME_DATABASE_POOL_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("MNEME_DATABASE_POOL_RECYCLE_SECONDS", "900")
    monkeypatch.setenv("MNEME_REDIS_URL", "redis://cache:6380/2")
    monkeypatch.setenv("MNEME_REDIS_MAX_CONNECTIONS", "20")
    monkeypatch.setenv("MNEME_ARXIV_MAX_RESULTS", "50")
    monkeypatch.setenv("MNEME_ARXIV_DAILY_CATEGORIES", "cs.CL, cs.AI,cs.CL")
    monkeypatch.setenv("MNEME_ARXIV_DAILY_MAX_RESULTS", "12")
    monkeypatch.setenv("MNEME_PAPER_STORAGE_DIR", "/var/lib/mneme/papers")
    monkeypatch.setenv("MNEME_PDF_MAX_BYTES", "1048576")
    monkeypatch.setenv("MNEME_PDF_DOWNLOAD_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("MNEME_PDF_DOWNLOAD_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("MNEME_PDF_MIN_TEXT_CHARS", "250")
    monkeypatch.setenv("MNEME_DEMO_TOKEN_SHA256", "a" * 64)
    monkeypatch.setenv("MNEME_DEMO_USER_ID", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
    monkeypatch.setenv("MNEME_DEEPSEEK_API_KEY", "deepseek-test-key")
    monkeypatch.setenv("MNEME_DEEPSEEK_THINKING_ENABLED", "true")
    monkeypatch.setenv("MNEME_AI_EMBEDDING_BACKEND", "fastembed")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.TESTING
    assert settings.debug is True
    assert settings.log_level == "warning"
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8080
    assert settings.api_workers == 4
    assert settings.api_timeout_seconds == 180
    assert settings.api_graceful_timeout_seconds == 45
    assert settings.api_keepalive_seconds == 10
    assert settings.api_max_requests == 2000
    assert settings.api_max_requests_jitter == 200
    assert settings.readiness_timeout_seconds == 3.5
    assert settings.database_pool_size == 8
    assert settings.database_max_overflow == 3
    assert settings.database_pool_timeout_seconds == 12.5
    assert settings.database_pool_recycle_seconds == 900
    assert str(settings.redis_url) == "redis://cache:6380/2"
    assert settings.redis_max_connections == 20
    assert settings.arxiv_max_results == 50
    assert settings.daily_arxiv_categories == ("cs.CL", "cs.AI")
    assert settings.arxiv_daily_max_results == 12
    assert settings.paper_storage_dir == Path("/var/lib/mneme/papers")
    assert settings.pdf_max_bytes == 1048576
    assert settings.pdf_download_timeout_seconds == 12.5
    assert settings.pdf_download_max_attempts == 5
    assert settings.pdf_min_text_chars == 250
    assert settings.demo_token_sha256 is not None
    assert settings.demo_token_sha256.get_secret_value() == "a" * 64
    assert str(settings.demo_user_id) == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "deepseek-test-key"
    assert settings.deepseek_thinking_enabled is True
    assert settings.ai_embedding_backend is EmbeddingBackend.FASTEMBED
    assert settings.use_json_logs is True


@pytest.mark.base
@pytest.mark.parametrize("timeout", ["0", "30.1"])
def test_readiness_timeout_is_bounded(
    monkeypatch: pytest.MonkeyPatch,
    timeout: str,
) -> None:
    monkeypatch.setenv("MNEME_READINESS_TIMEOUT_SECONDS", timeout)

    with pytest.raises(ValueError):
        Settings(_env_file=None)


@pytest.mark.base
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("database_pool_size", 0),
        ("database_pool_size", 51),
        ("database_max_overflow", -1),
        ("database_max_overflow", 51),
        ("database_pool_timeout_seconds", 0),
        ("database_pool_timeout_seconds", 301),
        ("database_pool_recycle_seconds", 0),
        ("database_pool_recycle_seconds", 86401),
    ],
)
def test_database_pool_settings_are_bounded(field: str, value: int) -> None:
    environment_name = f"MNEME_{field.upper()}"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(environment_name, str(value))
        with pytest.raises(ValueError):
            Settings(_env_file=None)


@pytest.mark.base
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("api_host", "0.0.0.0"),
        ("api_port", 1023),
        ("api_port", 65536),
        ("api_workers", 0),
        ("api_workers", 9),
        ("api_timeout_seconds", 0),
        ("api_timeout_seconds", 601),
        ("api_graceful_timeout_seconds", 0),
        ("api_graceful_timeout_seconds", 301),
        ("api_keepalive_seconds", 0),
        ("api_keepalive_seconds", 61),
        ("api_max_requests", -1),
        ("api_max_requests_jitter", -1),
    ],
)
def test_api_runtime_settings_are_bounded(field: str, value: int | str) -> None:
    environment_name = f"MNEME_{field.upper()}"
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv(environment_name, str(value))
        with pytest.raises(ValueError):
            Settings(_env_file=None)
