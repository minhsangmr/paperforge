"""Tests for readiness aggregation."""

import asyncio

from paperforge.core.config import OllamaSettings, OpenSearchSettings, RedisSettings, Settings
from paperforge.services.health import HealthService


class SyncProbeStub:
    def __init__(self, result: bool = True, error: Exception | None = None) -> None:
        self.result = result
        self.error = error

    def ping(self) -> bool:
        if self.error is not None:
            raise self.error
        return self.result


class AsyncProbeStub:
    def __init__(self, result: bool = True) -> None:
        self.result = result

    async def ping(self) -> bool:
        return self.result


def test_readiness_is_ready_when_enabled_dependencies_are_healthy() -> None:
    settings = Settings(
        ollama=OllamaSettings(enabled=False),
    )
    service = HealthService(
        settings=settings,
        database=SyncProbeStub(),
        opensearch=SyncProbeStub(),
        redis=SyncProbeStub(),
        ollama=None,
    )

    result = asyncio.run(service.readiness("0.2.0"))

    assert result.status == "ready"
    assert result.checks["ollama"].status == "disabled"


def test_optional_failure_degrades_without_failing_readiness() -> None:
    settings = Settings(redis=RedisSettings(enabled=True, required=False))
    service = HealthService(
        settings=settings,
        database=SyncProbeStub(),
        opensearch=SyncProbeStub(),
        redis=SyncProbeStub(error=RuntimeError("offline")),
        ollama=None,
    )

    result = asyncio.run(service.readiness("0.2.0"))

    assert result.status == "degraded"
    assert result.checks["redis"].detail == "health check failed"


def test_required_failure_makes_application_not_ready() -> None:
    settings = Settings(
        opensearch=OpenSearchSettings(enabled=True, required=True),
        redis=RedisSettings(enabled=False),
    )
    service = HealthService(
        settings=settings,
        database=SyncProbeStub(),
        opensearch=SyncProbeStub(result=False),
        redis=None,
        ollama=None,
    )

    result = asyncio.run(service.readiness("0.2.0"))

    assert result.status == "not_ready"
    assert result.checks["opensearch"].required is True
