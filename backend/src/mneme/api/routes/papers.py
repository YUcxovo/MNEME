"""Authenticated paper catalog endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.papers import Paper, PaperPage
from mneme.repositories.paper_catalog import (
    InvalidPaperCursorError,
    PaperCatalogRepository,
    decode_paper_cursor,
)

router = APIRouter(prefix="/papers", tags=["papers"])


@router.get(
    "",
    response_model=PaperPage,
    operation_id="listPapers",
    responses={"default": {"model": ErrorResponse}},
)
async def list_papers(
    _principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PaperCatalogRepository, Depends(get_paper_catalog_repository)],
    cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> PaperPage:
    """Return papers in stable descending publication order."""
    try:
        decoded_cursor = decode_paper_cursor(cursor) if cursor is not None else None
    except InvalidPaperCursorError:
        raise ApiError(
            status.HTTP_400_BAD_REQUEST,
            "invalid_cursor",
            "The pagination cursor is invalid.",
        ) from None

    page = await repository.list_papers(limit=limit, cursor=decoded_cursor)
    return PaperPage(
        items=[Paper.from_model(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{paper_id}",
    response_model=Paper,
    operation_id="getPaper",
    responses={"default": {"model": ErrorResponse}},
)
async def get_paper(
    paper_id: UUID,
    _principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PaperCatalogRepository, Depends(get_paper_catalog_repository)],
) -> Paper:
    """Return public metadata for one internal paper UUID."""
    paper = await repository.get_paper(paper_id)
    if paper is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )
    return Paper.from_model(paper)
