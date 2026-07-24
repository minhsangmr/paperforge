"""API tests for liveness, readiness, and request tracing."""

from typing import cast
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from paperforge.core.config import OllamaSettings, OpenSearchSettings, RedisSettings, Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.redis import RedisClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.main import create_app


def make_infrastructure(
    *,
    database_healthy: bool = True,
    opensearch_healthy: bool = True,
    redis_healthy: bool = True,
) -> Infrastructure:
    database = MagicMock()
    database.ping.return_value = database_healthy
    opensearch = MagicMock()
    opensearch.ping.return_value = opensearch_healthy
    redis = MagicMock()
    redis.ping.return_value = redis_healthy
    return Infrastructure(
        database=cast(Database, database),
        opensearch=cast(OpenSearchClient, opensearch),
        redis=cast(RedisClient, redis),
        ollama=None,
    )


def test_liveness_echoes_request_id() -> None:
    settings = Settings()
    app = create_app(settings, make_infrastructure())

    with TestClient(app) as client:
        response = client.get("/api/v1/health/live", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request"
    assert response.json()["version"] == "0.2.0"


def test_readiness_returns_200_for_optional_failure() -> None:
    settings = Settings(
        redis=RedisSettings(enabled=True, required=False),
        ollama=OllamaSettings(enabled=False),
    )
    app = create_app(settings, make_infrastructure(redis_healthy=False))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_readiness_returns_503_for_required_failure() -> None:
    settings = Settings(
        opensearch=OpenSearchSettings(enabled=True, required=True),
        redis=RedisSettings(enabled=False),
    )
    app = create_app(settings, make_infrastructure(opensearch_healthy=False))

    with TestClient(app) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
