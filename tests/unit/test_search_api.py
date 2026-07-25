"""API tests for GET and POST BM25 search."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from paperforge.core.config import Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.main import create_app
from paperforge.schemas.search import SearchHit, SearchResponse


def _infrastructure(response: SearchResponse) -> Infrastructure:
    database = MagicMock()
    opensearch = MagicMock()
    opensearch.search.return_value = response
    return Infrastructure(
        database=cast(Database, database),
        opensearch=cast(OpenSearchClient, opensearch),
        redis=None,
        ollama=None,
    )


def _response() -> SearchResponse:
    return SearchResponse(
        query="AI",
        total=1,
        page=1,
        page_size=10,
        took_ms=3,
        hits=[
            SearchHit(
                arxiv_id="2607.00001",
                title="AI Agents",
                authors=["Ada Lovelace"],
                abstract="Agent systems",
                categories=["cs.AI"],
                published_date=datetime.now(UTC),
                pdf_url="https://arxiv.org/pdf/2607.00001",
                pdf_processed=True,
                score=4.2,
            )
        ],
    )


def test_get_search_returns_ranked_results() -> None:
    app = create_app(Settings(), _infrastructure(_response()))

    with TestClient(app) as client:
        response = client.get("/api/v1/search", params={"q": "AI", "category": "cs.AI"})

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["hits"][0]["arxiv_id"] == "2607.00001"


def test_post_search_validates_date_range() -> None:
    app = create_app(Settings(), _infrastructure(_response()))

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/search",
            json={
                "query": "AI",
                "published_from": "2026-07-24",
                "published_to": "2026-07-01",
            },
        )

    assert response.status_code == 422


def test_search_is_503_when_opensearch_is_disabled() -> None:
    database = MagicMock()
    infrastructure = Infrastructure(
        database=cast(Database, database),
        opensearch=None,
        redis=None,
        ollama=None,
    )
    app = create_app(Settings(), infrastructure)

    with TestClient(app) as client:
        response = client.get("/api/v1/search", params={"q": "AI"})

    assert response.status_code == 503
