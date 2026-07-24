"""Health-check routes."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from paperforge import __version__

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
