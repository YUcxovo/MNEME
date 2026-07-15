"""Stable public error envelope and FastAPI exception handlers."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from mneme.api.middleware import REQUEST_ID_HEADER

logger = structlog.get_logger(__name__)


class ErrorResponse(BaseModel):
    """Shared machine-readable response returned for every HTTP error."""

    code: str
    message: str
    request_id: str
    details: dict[str, Any] | None = None


class ApiError(Exception):
    """Expected application error with a stable public representation."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        details: dict[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
        self.headers = dict(headers) if headers is not None else {}


def register_error_handlers(application: FastAPI) -> None:
    """Install all exception-to-envelope adapters on an application."""
    application.add_exception_handler(ApiError, handle_api_error)
    application.add_exception_handler(RequestValidationError, handle_validation_error)
    application.add_exception_handler(StarletteHTTPException, handle_http_error)
    application.add_exception_handler(SQLAlchemyError, handle_database_error)
    application.add_exception_handler(Exception, handle_unexpected_error)


async def handle_api_error(request: Request, exception: Exception) -> JSONResponse:
    """Render an expected application error without changing its stable code."""
    if not isinstance(exception, ApiError):
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
        )
    return _error_response(
        request,
        exception.status_code,
        exception.code,
        exception.message,
        details=exception.details,
        headers=exception.headers,
    )


async def handle_validation_error(request: Request, exception: Exception) -> JSONResponse:
    """Return useful validation metadata without echoing rejected input values."""
    errors: list[dict[str, object]] = []
    if isinstance(exception, RequestValidationError):
        errors = [
            {
                "location": list(error.get("loc", ())),
                "message": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "validation_error")),
            }
            for error in exception.errors()
        ]
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "validation_error",
        "The request did not satisfy the API contract.",
        details={"errors": errors},
    )


async def handle_http_error(request: Request, exception: Exception) -> JSONResponse:
    """Normalize framework-generated HTTP failures without returning raw details."""
    if not isinstance(exception, StarletteHTTPException):
        return _error_response(
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            "An unexpected error occurred.",
        )
    code = {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "authentication_required",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
        status.HTTP_405_METHOD_NOT_ALLOWED: "method_not_allowed",
        status.HTTP_409_CONFLICT: "conflict",
        status.HTTP_413_CONTENT_TOO_LARGE: "request_too_large",
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: "unsupported_media_type",
        status.HTTP_429_TOO_MANY_REQUESTS: "rate_limited",
        status.HTTP_503_SERVICE_UNAVAILABLE: "service_unavailable",
    }.get(exception.status_code, "http_error")
    try:
        message = HTTPStatus(exception.status_code).phrase
    except ValueError:
        message = "The request could not be completed."
    return _error_response(
        request,
        exception.status_code,
        code,
        message,
        headers=exception.headers,
    )


async def handle_database_error(request: Request, exception: Exception) -> JSONResponse:
    """Hide database diagnostics behind the stable dependency-failure response."""
    logger.error(
        "database_request_failed",
        request_id=_request_id(request),
        exception_type=type(exception).__name__,
        exc_info=exception,
    )
    return _error_response(
        request,
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "service_unavailable",
        "A required service is temporarily unavailable.",
    )


async def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
    """Log an unexpected exception and return a non-sensitive public response."""
    request_id = _request_id(request)
    logger.error(
        "unhandled_request_error",
        request_id=request_id,
        exception_type=type(exception).__name__,
        exc_info=exception,
    )
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred.",
    )


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    *,
    details: dict[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    request_id = _request_id(request)
    response_headers = dict(headers) if headers is not None else {}
    response_headers[REQUEST_ID_HEADER] = request_id
    payload = ErrorResponse(
        code=code,
        message=message,
        request_id=request_id,
        details=details,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(exclude_none=True),
        headers=response_headers,
    )


def _request_id(request: Request) -> str:
    request_id = getattr(request.state, "request_id", None)
    return request_id if isinstance(request_id, str) else str(uuid4())
