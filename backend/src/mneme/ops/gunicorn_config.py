"""Gunicorn configuration for the production FastAPI process."""

from mneme.core.config import get_settings

_settings = get_settings()

bind = f"{_settings.api_host}:{_settings.api_port}"
workers = _settings.api_workers
worker_class = "uvicorn_worker.UvicornWorker"
preload_app = False
forwarded_allow_ips = "127.0.0.1"
timeout = _settings.api_timeout_seconds
graceful_timeout = _settings.api_graceful_timeout_seconds
keepalive = _settings.api_keepalive_seconds
max_requests = _settings.api_max_requests
max_requests_jitter = _settings.api_max_requests_jitter

# stdout/stderr are collected by systemd and remain available through journald.
accesslog = None
errorlog = "-"
capture_output = False
