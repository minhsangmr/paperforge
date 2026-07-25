"""Tests for asynchronous BM25 search orchestration."""

from typing import cast
from unittest.mock import MagicMock

import pytest

from paperforge.core.config import OpenSearchSettings
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.schemas.search import SearchRequest, SearchResponse
from paperforge.services.search import SearchService


@pytest.mark.asyncio
async def test_search_service_runs_client_and_returns_response() -> None:
    client = MagicMock()
    expected = SearchResponse(
        query="AI",
        total=0,
        page=1,
        page_size=10,
        took_ms=1,
        hits=[],
    )
    client.search.return_value = expected
    service = SearchService(cast(OpenSearchClient, client), OpenSearchSettings())
    request = SearchRequest(query="AI")

    response = await service.search(request)

    assert response is expected
    client.search.assert_called_once_with(request)


@pytest.mark.asyncio
async def test_search_service_enforces_max_page_size() -> None:
    settings = OpenSearchSettings(max_page_size=20)
    service = SearchService(cast(OpenSearchClient, MagicMock()), settings)

    with pytest.raises(ValueError, match="page_size"):
        await service.search(SearchRequest(query="AI", page_size=21))


@pytest.mark.asyncio
async def test_search_service_enforces_result_window() -> None:
    settings = OpenSearchSettings(max_result_window=100, max_page_size=50)
    service = SearchService(cast(OpenSearchClient, MagicMock()), settings)

    with pytest.raises(ValueError, match="result window"):
        await service.search(SearchRequest(query="AI", page=3, page_size=50))
