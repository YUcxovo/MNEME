"""Tests for environment-backed settings."""

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
    assert settings.use_json_logs is False


@pytest.mark.base
def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MNEME_ENVIRONMENT", "testing")
    monkeypatch.setenv("MNEME_DEBUG", "true")
    monkeypatch.setenv("MNEME_LOG_LEVEL", "warning")
    monkeypatch.setenv("MNEME_REDIS_URL", "redis://cache:6380/2")
    monkeypatch.setenv("MNEME_REDIS_MAX_CONNECTIONS", "20")
    monkeypatch.setenv("MNEME_ARXIV_MAX_RESULTS", "50")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.TESTING
    assert settings.debug is True
    assert settings.log_level == "warning"
    assert str(settings.redis_url) == "redis://cache:6380/2"
    assert settings.redis_max_connections == 20
    assert settings.arxiv_max_results == 50
    assert settings.use_json_logs is True
