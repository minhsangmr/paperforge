"""Health endpoint response models."""

from typing import Literal

from pydantic import BaseModel


class ServiceCheck(BaseModel):
    """One dependency probe result."""

    status: Literal["healthy", "unhealthy", "disabled"]
    required: bool
    latency_ms: float | None = None
    detail: str | None = None


class ReadinessResponse(BaseModel):
    """Aggregated readiness state."""

    status: Literal["ready", "degraded", "not_ready"]
    service: str
    version: str
    environment: str
    checks: dict[str, ServiceCheck]
