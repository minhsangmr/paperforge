"""API tests for cache diagnostics and Langfuse feedback."""

from typing import cast
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient
from pydantic import SecretStr

from paperforge.core.config import LangfuseSettings, OllamaSettings, Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.resources import Infrastructure
from paperforge.main import create_app
from paperforge.services.observability.langfuse import LangfuseObservability


def _infrastructure(observability: LangfuseObservability | None = None) -> Infrastructure:
    database = MagicMock()
    database.close = MagicMock()
    return Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
        observability=observability,
    )


def test_cache_stats_and_invalidation_work_when_redis_disabled() -> None:
    app = create_app(Settings(ollama=OllamaSettings(enabled=False)), _infrastructure())
    with TestClient(app) as client:
        stats = client.get("/api/v1/cache/stats")
        invalidation = client.post("/api/v1/cache/invalidate", json={"query": "What is RAG?"})
    assert stats.status_code == 200
    assert stats.json()["enabled"] is False
    assert invalidation.status_code == 200
    assert invalidation.json()["deleted"] is False


def test_feedback_is_503_when_langfuse_disabled() -> None:
    settings = Settings(langfuse=LangfuseSettings(enabled=False))
    app = create_app(settings, _infrastructure(LangfuseObservability(settings.langfuse)))
    with TestClient(app) as client:
        response = client.post("/api/v1/feedback", json={"trace_id": "a" * 32, "value": 1})
    assert response.status_code == 503


def test_feedback_returns_confirmation() -> None:
    settings = Settings(
        langfuse=LangfuseSettings(
            enabled=True,
            public_key=SecretStr("pk"),
            secret_key=SecretStr("sk"),
        )
    )
    observability = MagicMock(spec=LangfuseObservability)
    observability.enabled = True
    observability.submit_feedback = AsyncMock(return_value=True)
    observability.close = AsyncMock()
    app = create_app(settings, _infrastructure(cast(LangfuseObservability, observability)))
    with TestClient(app) as client:
        response = client.post("/api/v1/feedback", json={"trace_id": "a" * 32, "value": 1})
    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "trace_id": "a" * 32,
        "score_name": "user-feedback",
    }
