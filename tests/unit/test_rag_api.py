"""API tests for complete and streaming Week 5 RAG."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from paperforge.api.dependencies import get_rag_service
from paperforge.core.config import OllamaSettings, Settings
from paperforge.exceptions import EmbeddingUnavailableError, OllamaGenerationError
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.main import create_app
from paperforge.schemas.hybrid_search import HybridSearchHit, HybridSearchResponse
from paperforge.schemas.rag import OllamaUsage
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.rag import RAGService


def _search_response() -> HybridSearchResponse:
    return HybridSearchResponse(
        query="grounded retrieval",
        requested_mode="auto",
        search_mode="bm25",
        embeddings_used=False,
        total=1,
        page=1,
        page_size=3,
        took_ms=1,
        hits=[
            HybridSearchHit(
                chunk_id="c1",
                chunk_index=0,
                arxiv_id="2607.00001",
                title="Grounded Retrieval",
                authors=["Ada Lovelace"],
                abstract="abstract",
                categories=["cs.IR"],
                published_date=datetime.now(UTC),
                pdf_url="https://arxiv.org/pdf/2607.00001.pdf",
                section_title="Methods",
                chunk_text="Evidence grounds generation.",
                score=1.0,
            )
        ],
    )


def _infrastructure() -> Infrastructure:
    database = MagicMock()
    hybrid = MagicMock()
    hybrid.search.return_value = _search_response()
    embeddings = MagicMock()
    embeddings.available = False
    embeddings.close = AsyncMock()
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=("Answer [S1]", OllamaUsage(prompt_tokens=3, completion_tokens=2))
    )
    ollama.close = AsyncMock()

    async def generate_stream(**_: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"response": "Answer", "done": True, "eval_count": 1}

    ollama.generate_stream = generate_stream
    return Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=cast(OllamaClient, ollama),
        hybrid_search=cast(HybridSearchClient, hybrid),
        embeddings=cast(JinaEmbeddingsClient, embeddings),
    )


def test_ask_returns_grounded_response() -> None:
    settings = Settings(ollama=OllamaSettings(enabled=True))
    app = create_app(settings, _infrastructure())

    with TestClient(app) as client:
        response = client.post("/api/v1/ask", json={"query": "What is retrieval?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Answer [S1]"
    assert response.json()["sources"][0]["citation"] == "S1"


def test_stream_uses_sse_content_type_and_events() -> None:
    settings = Settings(ollama=OllamaSettings(enabled=True))
    app = create_app(settings, _infrastructure())

    with TestClient(app) as client:
        response = client.post("/api/v1/stream", json={"query": "What is retrieval?"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: metadata" in response.text
    assert "event: token" in response.text
    assert "event: done" in response.text


def test_rag_is_503_when_ollama_disabled() -> None:
    infrastructure = _infrastructure()
    infrastructure.ollama = None
    app = create_app(Settings(ollama=OllamaSettings(enabled=False)), infrastructure)

    with TestClient(app) as client:
        response = client.post("/api/v1/ask", json={"query": "Question"})

    assert response.status_code == 503
    assert response.json()["detail"] == "Ollama generation is disabled"


def test_ask_maps_expected_service_errors() -> None:
    for error, status_code in [
        (EmbeddingUnavailableError("missing key"), 503),
        (OllamaGenerationError("model unavailable"), 503),
        (ValueError("bad limit"), 422),
        (RuntimeError("boom"), 503),
    ]:
        app = create_app(Settings(ollama=OllamaSettings(enabled=True)), _infrastructure())
        service = MagicMock()
        service.answer = AsyncMock(side_effect=error)
        app.dependency_overrides[get_rag_service] = lambda service=service: cast(
            RAGService, service
        )
        with TestClient(app) as client:
            response = client.post("/api/v1/ask", json={"query": "Question"})
        assert response.status_code == status_code


def test_stream_serializes_expected_and_unexpected_errors() -> None:
    async def expected_stream(_: object) -> AsyncIterator[object]:
        raise OllamaGenerationError("stream failed")
        yield

    async def unexpected_stream(_: object) -> AsyncIterator[object]:
        raise RuntimeError("boom")
        yield

    for stream, message in [
        (expected_stream, "stream failed"),
        (unexpected_stream, "temporarily unavailable"),
    ]:
        app = create_app(Settings(ollama=OllamaSettings(enabled=True)), _infrastructure())
        service = MagicMock()
        service.stream = stream
        app.dependency_overrides[get_rag_service] = lambda service=service: cast(
            RAGService, service
        )
        with TestClient(app) as client:
            response = client.post("/api/v1/stream", json={"query": "Question"})
        assert response.status_code == 200
        assert "event: error" in response.text
        assert message in response.text
