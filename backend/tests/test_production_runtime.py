"""Tests for the production ASGI process configuration."""

import importlib

import pytest

from mneme.core.config import get_settings
from mneme.ops import gunicorn_config


@pytest.mark.base
def test_gunicorn_defaults_bind_only_to_loopback() -> None:
    assert gunicorn_config.bind == "127.0.0.1:8000"
    assert gunicorn_config.workers == 2
    assert gunicorn_config.worker_class == "uvicorn_worker.UvicornWorker"
    assert gunicorn_config.timeout == 120
    assert gunicorn_config.graceful_timeout == 90
    assert gunicorn_config.keepalive == 5
    assert gunicorn_config.max_requests == 1000
    assert gunicorn_config.max_requests_jitter == 100
    assert gunicorn_config.accesslog is None
    assert gunicorn_config.preload_app is False
    assert gunicorn_config.forwarded_allow_ips == "127.0.0.1"
    assert gunicorn_config.errorlog == "-"


@pytest.mark.base
def test_gunicorn_configuration_reads_prefixed_environment() -> None:
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("MNEME_API_PORT", "8080")
        monkeypatch.setenv("MNEME_API_WORKERS", "3")
        monkeypatch.setenv("MNEME_API_TIMEOUT_SECONDS", "180")
        monkeypatch.setenv("MNEME_API_GRACEFUL_TIMEOUT_SECONDS", "45")
        monkeypatch.setenv("MNEME_API_KEEPALIVE_SECONDS", "10")
        monkeypatch.setenv("MNEME_API_MAX_REQUESTS", "2000")
        monkeypatch.setenv("MNEME_API_MAX_REQUESTS_JITTER", "250")
        get_settings.cache_clear()

        reloaded = importlib.reload(gunicorn_config)

        assert reloaded.bind == "127.0.0.1:8080"
        assert reloaded.workers == 3
        assert reloaded.timeout == 180
        assert reloaded.graceful_timeout == 45
        assert reloaded.keepalive == 10
        assert reloaded.max_requests == 2000
        assert reloaded.max_requests_jitter == 250

    get_settings.cache_clear()
    importlib.reload(gunicorn_config)
