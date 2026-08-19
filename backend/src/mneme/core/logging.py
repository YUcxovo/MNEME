"""Structured logging configuration."""

import logging

import structlog

from mneme.core.config import Settings


def configure_logging(settings: Settings) -> None:
    """Configure standard-library logging and structlog once at application startup."""
    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer: structlog.types.Processor
    if settings.use_json_logs:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    logging.basicConfig(
        format="%(message)s",
        level=settings.log_level.upper(),
        force=True,
    )
    # httpx logs complete request URLs at INFO and httpcore exposes them at
    # DEBUG.  Query strings can contain provider credentials or user-entered
    # interests, so application logs must not inherit those verbose levels.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(settings.log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
