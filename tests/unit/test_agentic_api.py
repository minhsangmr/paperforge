from typing import cast
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from paperforge.api import dependencies
from paperforge.core.config import Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.resources import Infrastructure
from paperforge.main import create_app
from paperforge.schemas.agentic import AgenticRAGResponse, GuardrailResult


def infrastructure() -> Infrastructure:
    database = MagicMock()
    database.ping.return_value = True
    return Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
    )


def result(query: str) -> AgenticRAGResponse:
    return AgenticRAGResponse(
        query=query,
        answer="Grounded answer.",
        sources=[],
        chunks_used=0,
        search_mode="bm25",
        model="llama3.2:1b",
        reasoning_steps=[],
        retrieval_attempts=1,
        guardrail=GuardrailResult(score=90, reason="research", accepted=True),
        status="completed",
    )


def test_agentic_endpoint_uses_request_controls() -> None:
    service = AsyncMock()
    service.answer.return_value = result("What is RAG?")
    app = create_app(Settings(), infrastructure())
    app.dependency_overrides[dependencies.get_agentic_rag_service] = lambda: service
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agentic-ask",
            json={"query": "What is RAG?", "top_k": 4, "max_retrieval_attempts": 3},
        )
    assert response.status_code == 200
    request = service.answer.await_args.args[0]
    assert request.top_k == 4
    assert request.max_retrieval_attempts == 3


def test_agentic_compatibility_alias() -> None:
    service = AsyncMock()
    service.answer.return_value = result("RAG")
    app = create_app(Settings(), infrastructure())
    app.dependency_overrides[dependencies.get_agentic_rag_service] = lambda: service
    with TestClient(app) as client:
        response = client.post("/api/v1/ask-agentic", json={"query": "RAG"})
    assert response.status_code == 200


def test_agentic_endpoint_maps_validation_error() -> None:
    service = AsyncMock()
    service.answer.side_effect = ValueError("bad request")
    app = create_app(Settings(), infrastructure())
    app.dependency_overrides[dependencies.get_agentic_rag_service] = lambda: service
    with TestClient(app) as client:
        response = client.post("/api/v1/agentic-ask", json={"query": "RAG"})
    assert response.status_code == 422


def test_agentic_endpoint_maps_unexpected_error() -> None:
    service = AsyncMock()
    service.answer.side_effect = RuntimeError("boom")
    app = create_app(Settings(), infrastructure())
    app.dependency_overrides[dependencies.get_agentic_rag_service] = lambda: service
    with TestClient(app) as client:
        response = client.post("/api/v1/agentic-ask", json={"query": "RAG"})
    assert response.status_code == 503
