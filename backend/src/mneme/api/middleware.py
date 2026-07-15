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
    supplied_request_id = request.headers.get(REQUEST_ID_HEADER)
    request_id = (
        supplied_request_id
        if supplied_request_id is not None and is_safe_request_id(supplied_request_id)
        else str(uuid4())
    )
    request.state.request_id = request_id
    started_at = perf_counter()
    clear_contextvars()
    bind_contextvars(
        request_id=request_id,
        http_method=request.method,
        http_path=request.url.path,
    )

    try:
        try:
            response = await call_next(request)
        except Exception as exception:
            # This middleware sits inside Starlette's debug error page. Rendering here keeps
            # the public envelope non-sensitive even when local debug logging is enabled.
            from mneme.api.errors import handle_unexpected_error

            response = await handle_unexpected_error(request, exception)
        response.headers[REQUEST_ID_HEADER] = request_id
        logger.info(
            "request_completed",
            http_status=response.status_code,
            duration_ms=_elapsed_ms(started_at),
        )
        return response
    finally:
        clear_contextvars()


def is_safe_request_id(value: str) -> bool:
    """Accept a compact printable ASCII request ID suitable for logs and headers."""
    return 1 <= len(value) <= 128 and all(0x21 <= ord(character) <= 0x7E for character in value)


def _elapsed_ms(started_at: float) -> float:
    """Return elapsed milliseconds rounded for compact logs."""
    return round((perf_counter() - started_at) * 1000, 3)
