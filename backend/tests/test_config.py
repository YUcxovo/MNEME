"""Tests for environment-backed settings."""

from pathlib import Path

import pytest

from mneme.core.config import Environment, Settings


@pytest.mark.base
def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert str(settings.redis_url) == "redis://localhost:6379/0"
    assert settings.redis_max_connections == 10
    assert str(settings.arxiv_api_url) == "https://export.arxiv.org/api/query"
    assert settings.arxiv_request_interval_seconds == 3
    assert settings.arxiv_max_results == 100
    assert settings.paper_storage_dir == Path(".data/papers")
    assert settings.pdf_max_bytes == 50 * 1024 * 1024
    assert settings.pdf_download_timeout_seconds == 60
    assert settings.pdf_download_max_attempts == 3
    assert settings.pdf_min_text_chars == 500
    assert settings.demo_token_sha256 is None
    assert settings.demo_user_id is None
    assert settings.use_json_logs is False


@pytest.mark.base
def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MNEME_ENVIRONMENT", "testing")
    monkeypatch.setenv("MNEME_DEBUG", "true")
    monkeypatch.setenv("MNEME_LOG_LEVEL", "warning")
    monkeypatch.setenv("MNEME_REDIS_URL", "redis://cache:6380/2")
    monkeypatch.setenv("MNEME_REDIS_MAX_CONNECTIONS", "20")
    monkeypatch.setenv("MNEME_ARXIV_MAX_RESULTS", "50")
    monkeypatch.setenv("MNEME_PAPER_STORAGE_DIR", "/var/lib/mneme/papers")
    monkeypatch.setenv("MNEME_PDF_MAX_BYTES", "1048576")
    monkeypatch.setenv("MNEME_PDF_DOWNLOAD_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("MNEME_PDF_DOWNLOAD_MAX_ATTEMPTS", "5")
    monkeypatch.setenv("MNEME_PDF_MIN_TEXT_CHARS", "250")
    monkeypatch.setenv("MNEME_DEMO_TOKEN_SHA256", "a" * 64)
    monkeypatch.setenv("MNEME_DEMO_USER_ID", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.TESTING
    assert settings.debug is True
    assert settings.log_level == "warning"
    assert str(settings.redis_url) == "redis://cache:6380/2"
    assert settings.redis_max_connections == 20
    assert settings.arxiv_max_results == 50
    assert settings.paper_storage_dir == Path("/var/lib/mneme/papers")
    assert settings.pdf_max_bytes == 1048576
    assert settings.pdf_download_timeout_seconds == 12.5
    assert settings.pdf_download_max_attempts == 5
    assert settings.pdf_min_text_chars == 250
    assert settings.demo_token_sha256 is not None
    assert settings.demo_token_sha256.get_secret_value() == "a" * 64
    assert str(settings.demo_user_id) == "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    assert settings.use_json_logs is True
