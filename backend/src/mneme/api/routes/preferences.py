"""Explicit preference endpoints for the authenticated demo user."""

from typing import Annotated

from fastapi import APIRouter, Depends, status

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_preference_repository
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.preferences import Preferences, PreferenceUpdate
from mneme.repositories.preferences import PreferenceRepository, PreferenceSnapshot

router = APIRouter(prefix="/users/me/preferences", tags=["preferences"])


def _to_response(snapshot: PreferenceSnapshot) -> Preferences:
    return Preferences(
        topics=snapshot.topics,
        followed_authors=snapshot.followed_authors,
        model_version=snapshot.model_version,
        updated_at=snapshot.updated_at,
    )


def _user_not_found() -> ApiError:
    return ApiError(
        status.HTTP_404_NOT_FOUND,
        "user_not_found",
        "The configured demo user has not been bootstrapped.",
    )


@router.get(
    "",
    response_model=Preferences,
    operation_id="getPreferences",
    responses={"default": {"model": ErrorResponse}},
)
async def get_preferences(
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PreferenceRepository, Depends(get_preference_repository)],
) -> Preferences:
    """Return both explicit preference lists and their model version."""
    snapshot = await repository.get_preferences(principal.user_id)
    if snapshot is None:
        raise _user_not_found()
    return _to_response(snapshot)


@router.put(
    "",
    response_model=Preferences,
    operation_id="updatePreferences",
    responses={"default": {"model": ErrorResponse}},
)
async def update_preferences(
    update: PreferenceUpdate,
    principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PreferenceRepository, Depends(get_preference_repository)],
) -> Preferences:
    """Completely replace the authenticated user's explicit preferences."""
    snapshot = await repository.replace_preferences(
        principal.user_id,
        topics=update.topics,
        followed_authors=update.followed_authors,
    )
    if snapshot is None:
        raise _user_not_found()
    return _to_response(snapshot)
