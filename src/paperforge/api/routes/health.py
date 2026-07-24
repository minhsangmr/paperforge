"""Liveness and readiness routes."""

from typing import Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from paperforge import __version__
from paperforge.api.dependencies import HealthServiceDep
from paperforge.schemas.health import ReadinessResponse

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Response returned when the API process is alive."""

    status: Literal["ok"] = "ok"
    service: Literal["paperforge"] = "paperforge"
    version: str


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Confirm that the FastAPI process is running."""

    return LivenessResponse(version=__version__)


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(
    health_service: HealthServiceDep,
    response: Response,
) -> ReadinessResponse:
    """Report required and optional dependency health."""

    result = await health_service.readiness(__version__)
    if result.status == "not_ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result
