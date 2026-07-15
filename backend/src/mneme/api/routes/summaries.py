"""Authenticated AI summary endpoint (Milestone 1: mock contract)."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.catalog import get_paper_catalog_repository
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.summaries import Summary
from mneme.repositories.paper_catalog import PaperCatalogRepository

router = APIRouter(prefix="/papers", tags=["ai"])


@router.get(
    "/{paper_id}/summary",
    response_model=Summary,
    operation_id="getPaperSummary",
    responses={"default": {"model": ErrorResponse}},
)
async def get_paper_summary(
    paper_id: UUID,
    _principal: Annotated[Principal, Depends(require_principal)],
    repository: Annotated[PaperCatalogRepository, Depends(get_paper_catalog_repository)],
) -> Summary:
    """Return a summary for one paper.

    Milestone 1 serves a deterministic abstract-derived placeholder that
    satisfies the frozen contract; Milestone 2 swaps in cached or async LLM
    generation (202 + Job) without changing the response shape.
    """
    paper = await repository.get_paper(paper_id)
    if paper is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )
    return Summary.mock_from_paper(paper)
