"""Service health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Public health-check response."""

    status: Literal["ok"]


@router.get("/health", response_model=HealthResponse, operation_id="getHealth")
async def get_health() -> HealthResponse:
    """Report that the application process is available."""
    return HealthResponse(status="ok")
