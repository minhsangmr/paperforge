"""Dependency readiness aggregation."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from time import perf_counter
from typing import Literal, Protocol

from paperforge.core.config import Settings
from paperforge.schemas.health import ReadinessResponse, ServiceCheck

logger = logging.getLogger(__name__)


class SyncProbe(Protocol):
    """Synchronous infrastructure health probe."""

    def ping(self) -> bool: ...


class AsyncProbe(Protocol):
    """Asynchronous infrastructure health probe."""

    async def ping(self) -> bool: ...


class HealthService:
    """Probe dependencies concurrently and classify readiness."""

    def __init__(
        self,
        *,
        settings: Settings,
        database: SyncProbe,
        opensearch: SyncProbe | None,
        redis: SyncProbe | None,
        ollama: AsyncProbe | None,
    ) -> None:
        self._settings = settings
        self._database = database
        self._opensearch = opensearch
        self._redis = redis
        self._ollama = ollama

    async def readiness(self, version: str) -> ReadinessResponse:
        """Return aggregate readiness without raising dependency errors."""

        checks_list = await asyncio.gather(
            self._run_sync("postgresql", self._database.ping, required=True),
            self._optional_sync(
                "opensearch",
                self._opensearch,
                enabled=self._settings.opensearch.enabled,
                required=self._settings.opensearch.required,
            ),
            self._optional_sync(
                "redis",
                self._redis,
                enabled=self._settings.redis.enabled,
                required=self._settings.redis.required,
            ),
            self._optional_async(
                "ollama",
                self._ollama,
                enabled=self._settings.ollama.enabled,
                required=self._settings.ollama.required,
            ),
        )
        checks = dict(checks_list)

        required_failure = any(
            check.required and check.status != "healthy" for check in checks.values()
        )
        optional_failure = any(
            not check.required and check.status == "unhealthy" for check in checks.values()
        )

        status: Literal["ready", "degraded", "not_ready"]
        if required_failure:
            status = "not_ready"
        elif optional_failure:
            status = "degraded"
        else:
            status = "ready"

        return ReadinessResponse(
            status=status,
            service=self._settings.service_name,
            version=version,
            environment=self._settings.environment,
            checks=checks,
        )

    async def _optional_sync(
        self,
        name: str,
        probe: SyncProbe | None,
        *,
        enabled: bool,
        required: bool,
    ) -> tuple[str, ServiceCheck]:
        if not enabled:
            return name, ServiceCheck(status="disabled", required=required)
        if probe is None:
            return name, ServiceCheck(
                status="unhealthy", required=required, detail="not configured"
            )
        return await self._run_sync(name, probe.ping, required=required)

    async def _optional_async(
        self,
        name: str,
        probe: AsyncProbe | None,
        *,
        enabled: bool,
        required: bool,
    ) -> tuple[str, ServiceCheck]:
        if not enabled:
            return name, ServiceCheck(status="disabled", required=required)
        if probe is None:
            return name, ServiceCheck(
                status="unhealthy", required=required, detail="not configured"
            )
        return await self._run_async(name, probe.ping, required=required)

    async def _run_sync(
        self,
        name: str,
        probe: Callable[[], bool],
        *,
        required: bool,
    ) -> tuple[str, ServiceCheck]:
        return await self._execute(name, lambda: asyncio.to_thread(probe), required=required)

    async def _run_async(
        self,
        name: str,
        probe: Callable[[], Awaitable[bool]],
        *,
        required: bool,
    ) -> tuple[str, ServiceCheck]:
        return await self._execute(name, probe, required=required)

    async def _execute(
        self,
        name: str,
        probe: Callable[[], Awaitable[bool]],
        *,
        required: bool,
    ) -> tuple[str, ServiceCheck]:
        started_at = perf_counter()
        try:
            healthy = await probe()
        except Exception:
            logger.exception("dependency.health_check_failed", extra={"dependency": name})
            healthy = False
        latency_ms = round((perf_counter() - started_at) * 1000, 2)
        return name, ServiceCheck(
            status="healthy" if healthy else "unhealthy",
            required=required,
            latency_ms=latency_ms,
            detail=None if healthy else "health check failed",
        )
