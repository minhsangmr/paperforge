"""Tests for readiness aggregation."""

import asyncio

from pydantic import SecretStr

from paperforge.core.config import (
    LangfuseSettings,
    OllamaSettings,
    OpenSearchSettings,
    RedisSettings,
    Settings,
)
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
        langfuse=LangfuseSettings(enabled=False),
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
    assert result.checks["langfuse"].status == "disabled"


def test_optional_failure_degrades_without_failing_readiness() -> None:
    settings = Settings(
        redis=RedisSettings(enabled=True, required=False),
        ollama=OllamaSettings(enabled=False),
        langfuse=LangfuseSettings(enabled=False),
    )
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
        ollama=OllamaSettings(enabled=False),
        langfuse=LangfuseSettings(enabled=False),
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


def test_optional_langfuse_failure_degrades_readiness() -> None:
    settings = Settings(
        ollama=OllamaSettings(enabled=False),
        langfuse=LangfuseSettings(
            enabled=True,
            required=False,
            public_key=SecretStr("pk-test"),
            secret_key=SecretStr("sk-test"),
        ),
    )
    service = HealthService(
        settings=settings,
        database=SyncProbeStub(),
        opensearch=SyncProbeStub(),
        redis=SyncProbeStub(),
        ollama=None,
        langfuse=AsyncProbeStub(result=False),
    )

    result = asyncio.run(service.readiness("0.7.0"))

    assert result.status == "degraded"
    assert result.checks["langfuse"].status == "unhealthy"
    assert result.checks["langfuse"].required is False
