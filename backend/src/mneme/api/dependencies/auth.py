"""Authentication dependency for the pre-provisioned MVP demo user."""

import re
from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from mneme.api.errors import ApiError
from mneme.core.config import Settings
from mneme.core.security import token_matches_sha256

_SHA256_HEX = re.compile(r"[0-9a-fA-F]{64}\Z")

demo_token = HTTPBearer(
    auto_error=False,
    bearerFormat="opaque-demo-token",
    description="Pre-provisioned opaque token for the Mneme MVP demo user.",
    scheme_name="demoToken",
)


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated identity made available to protected endpoint handlers."""

    user_id: UUID


async def require_principal(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(demo_token)],
) -> Principal:
    """Validate the configured demo token without querying or exposing user data."""
    settings: Settings = request.app.state.settings
    configured_secret = settings.demo_token_sha256
    user_id = settings.demo_user_id
    configured_digest = (
        configured_secret.get_secret_value() if configured_secret is not None else None
    )

    if (
        configured_digest is None
        or user_id is None
        or _SHA256_HEX.fullmatch(configured_digest) is None
    ):
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "service_unavailable",
            "Authentication is not configured.",
        )

    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "authentication_required",
            "A Bearer token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not token_matches_sha256(credentials.credentials, configured_digest):
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED,
            "invalid_token",
            "The Bearer token is invalid.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return Principal(user_id=user_id)
