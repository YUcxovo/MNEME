"""Shared HTTP middleware."""

from collections.abc import Awaitable, Callable
from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request, Response
from structlog.contextvars import bind_contextvars, clear_contextvars

REQUEST_ID_HEADER = "X-Request-ID"
logger = structlog.get_logger(__name__)


async def request_context_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """Attach a request ID and emit one safe structured access log per request."""
    request_id = request.headers.get(REQUEST_ID_HEADER, str(uuid4()))
    started_at = perf_counter()
    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        http_method=request.method,
        http_path=request.url.path,
    )

    try:
        response = await call_next(request)
    except Exception:
        logger.exception("request_failed", duration_ms=_elapsed_ms(started_at))
        raise
    else:
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            http_status=response.status_code,
            duration_ms=_elapsed_ms(started_at),
        )
        return response
    finally:
        clear_contextvars()


def _elapsed_ms(started_at: float) -> float:
    """Return elapsed milliseconds rounded for compact logs."""
    return round((perf_counter() - started_at) * 1000, 3)
