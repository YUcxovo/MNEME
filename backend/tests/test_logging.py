"""Logging privacy regression tests."""

import logging

from mneme.core.config import Settings
from mneme.core.logging import configure_logging


def test_http_clients_do_not_log_request_urls_at_debug_level(monkeypatch) -> None:
    """Provider keys and user topics in query strings stay out of app logs."""
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    monkeypatch.setattr(httpx_logger, "level", httpx_logger.level)
    monkeypatch.setattr(httpcore_logger, "level", httpcore_logger.level)
    monkeypatch.setattr(logging, "basicConfig", lambda **_: None)
    monkeypatch.setattr("mneme.core.logging.structlog.configure", lambda **_: None)

    configure_logging(Settings(_env_file=None, log_level="DEBUG"))

    assert not httpx_logger.isEnabledFor(logging.INFO)
    assert not httpcore_logger.isEnabledFor(logging.DEBUG)
