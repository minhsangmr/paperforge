"""API tests for unified Week 4 retrieval."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from paperforge.core.config import HybridSearchSettings, Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.main import create_app
from paperforge.schemas.hybrid_search import HybridSearchHit, HybridSearchResponse
from paperforge.services.embeddings.jina import JinaEmbeddingsClient


def _response() -> HybridSearchResponse:
    return HybridSearchResponse(
        query="semantic retrieval",
        requested_mode="auto",
        search_mode="bm25",
        embeddings_used=False,
        total=1,
        page=1,
        page_size=10,
        took_ms=4,
        hits=[
            HybridSearchHit(
                chunk_id="c1",
                chunk_index=0,
                arxiv_id="2607.00001",
                title="Hybrid Retrieval",
                authors=["Ada Lovelace"],
                abstract="A search paper",
                categories=["cs.IR"],
                published_date=datetime.now(UTC),
                pdf_url="https://arxiv.org/pdf/2607.00001",
                section_title="Introduction",
                chunk_text="semantic and lexical retrieval",
                score=0.8,
            )
        ],
    )


def _infrastructure(*, configured: bool = True) -> Infrastructure:
    database = MagicMock()
    hybrid = MagicMock()
    hybrid.search.return_value = _response()
    embeddings = MagicMock()
    embeddings.available = configured
    embeddings.close = AsyncMock()
    return Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
        hybrid_search=cast(HybridSearchClient, hybrid),
        embeddings=cast(JinaEmbeddingsClient, embeddings),
    )


def test_hybrid_search_auto_falls_back_to_bm25() -> None:
    app = create_app(Settings(), _infrastructure(configured=False))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/hybrid-search",
            json={"query": "semantic retrieval", "mode": "auto"},
        )

    assert response.status_code == 200
    assert response.json()["search_mode"] == "bm25"
    assert response.json()["hits"][0]["chunk_id"] == "c1"


def test_explicit_vector_is_503_without_embedding_key() -> None:
    app = create_app(Settings(), _infrastructure(configured=False))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/hybrid-search",
            json={"query": "semantic retrieval", "mode": "vector"},
        )

    assert response.status_code == 503
    assert "API_KEY" in response.json()["detail"]


def test_hybrid_route_is_503_when_feature_disabled() -> None:
    database = MagicMock()
    infrastructure = Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
    )
    app = create_app(Settings(), infrastructure)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/hybrid-search",
            json={"query": "semantic retrieval"},
        )

    assert response.status_code == 503


def test_hybrid_route_normalizes_unexpected_failure() -> None:
    infrastructure = _infrastructure(configured=False)
    assert infrastructure.hybrid_search is not None
    hybrid = cast(MagicMock, infrastructure.hybrid_search)
    hybrid.search.side_effect = RuntimeError("boom")
    app = create_app(Settings(), infrastructure)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/hybrid-search",
            json={"query": "semantic retrieval", "mode": "auto"},
        )

    assert response.status_code == 503
    assert response.json()["detail"] == "hybrid search is temporarily unavailable"


def test_hybrid_route_returns_422_for_public_limit_violation() -> None:
    settings = Settings(hybrid_search=HybridSearchSettings(default_page_size=5, max_page_size=5))
    app = create_app(settings, _infrastructure(configured=False))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/hybrid-search",
            json={"query": "semantic retrieval", "page_size": 6},
        )

    assert response.status_code == 422
    assert "page_size" in response.json()["detail"]
