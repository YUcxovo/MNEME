"""Service health endpoint."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class Health(BaseModel):
    """Public health-check response."""

    status: Literal["ok"]


@router.get("/health", response_model=Health, operation_id="getHealth")
async def get_health() -> Health:
    """Report that the application process is available."""
    return Health(status="ok")
