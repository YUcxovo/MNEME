"""Authenticated paper-centered citation graph endpoint."""

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.graph import get_graph_preparation_service, get_graph_service
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.graphs import Graph
from mneme.services.graph import GraphService
from mneme.services.graph_preparation import GraphPreparationService

router = APIRouter(prefix="/graph", tags=["graph"])
_PREPARATION_NEIGHBOR_LIMIT: Final = 20


@router.get(
    "/{paper_id}",
    response_model=Graph,
    operation_id="getPaperGraph",
    responses={"default": {"model": ErrorResponse}},
)
async def get_paper_graph(
    paper_id: UUID,
    _principal: Annotated[Principal, Depends(require_principal)],
    service: Annotated[GraphService, Depends(get_graph_service)],
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Graph:
    """Return an algorithm-enriched bounded neighborhood for one paper."""
    result = await service.get_graph(paper_id, depth=depth, limit=limit)
    if result is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )
    return Graph.from_result(result)


@router.post(
    "/{paper_id}/prepare",
    response_model=Graph,
    operation_id="preparePaperGraph",
    responses={"default": {"model": ErrorResponse}},
)
async def prepare_paper_graph(
    paper_id: UUID,
    _principal: Annotated[Principal, Depends(require_principal)],
    preparation: Annotated[
        GraphPreparationService,
        Depends(get_graph_preparation_service),
    ],
    service: Annotated[GraphService, Depends(get_graph_service)],
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> Graph:
    """Prepare real local citation edges on demand, then return the standard graph."""
    outcome = await preparation.prepare(
        paper_id,
        neighbor_limit=_PREPARATION_NEIGHBOR_LIMIT,
    )
    if outcome is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )
    result = await service.get_graph(paper_id, depth=depth, limit=limit)
    if result is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            "paper_not_found",
            "The requested paper does not exist.",
        )
    return Graph.from_result(result)
