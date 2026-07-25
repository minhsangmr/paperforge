"""Asynchronous application service for BM25 queries."""

import asyncio

from paperforge.core.config import OpenSearchSettings
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.schemas.search import SearchRequest, SearchResponse


class SearchService:
    """Validate public query limits and keep blocking I/O off the event loop."""

    def __init__(self, client: OpenSearchClient, settings: OpenSearchSettings) -> None:
        self._client = client
        self._settings = settings

    async def search(self, request: SearchRequest) -> SearchResponse:
        """Execute one BM25 query in a worker thread."""

        if request.page_size > self._settings.max_page_size:
            raise ValueError(f"page_size cannot exceed {self._settings.max_page_size}")
        if request.offset + request.page_size > self._settings.max_result_window:
            raise ValueError(
                f"requested page exceeds max result window {self._settings.max_result_window}"
            )
        return await asyncio.to_thread(self._client.search, request)
