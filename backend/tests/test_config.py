"""Tests for environment-backed settings."""

import pytest

from mneme.core.config import Environment, Settings


@pytest.mark.base
def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment is Environment.DEVELOPMENT
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.use_json_logs is False


@pytest.mark.base
def test_settings_read_prefixed_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MNEME_ENVIRONMENT", "testing")
    monkeypatch.setenv("MNEME_DEBUG", "true")
    monkeypatch.setenv("MNEME_LOG_LEVEL", "warning")

    settings = Settings(_env_file=None)

    assert settings.environment is Environment.TESTING
    assert settings.debug is True
    assert settings.log_level == "warning"
    assert settings.use_json_logs is True
