"""Authenticated paper-centered citation graph endpoint."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from mneme.api.dependencies.auth import Principal, require_principal
from mneme.api.dependencies.graph import get_graph_service
from mneme.api.errors import ApiError, ErrorResponse
from mneme.api.schemas.graphs import Graph
from mneme.services.graph import GraphService

router = APIRouter(prefix="/graph", tags=["graph"])


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
