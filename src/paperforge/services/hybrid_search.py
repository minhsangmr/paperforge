"""Application service for automatic BM25/vector/hybrid retrieval."""

import asyncio
from typing import cast

from paperforge.core.config import HybridSearchSettings
from paperforge.exceptions import EmbeddingUnavailableError
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.schemas.hybrid_search import (
    HybridSearchRequest,
    HybridSearchResponse,
    ResolvedSearchMode,
)
from paperforge.services.embeddings.jina import JinaEmbeddingsClient


class HybridSearchService:
    """Resolve search mode, generate query vectors, and offload blocking I/O."""

    def __init__(
        self,
        client: HybridSearchClient,
        embeddings: JinaEmbeddingsClient,
        settings: HybridSearchSettings,
    ) -> None:
        self._client = client
        self._embeddings = embeddings
        self._settings = settings

    async def search(self, request: HybridSearchRequest) -> HybridSearchResponse:
        """Execute the requested mode, with auto falling back to BM25 safely."""

        if request.page_size > self._settings.max_page_size:
            raise ValueError(f"page_size cannot exceed {self._settings.max_page_size}")
        if request.offset + request.page_size > self._settings.max_result_window:
            raise ValueError(
                f"requested page exceeds max result window {self._settings.max_result_window}"
            )

        mode: ResolvedSearchMode
        query_vector: list[float] | None = None
        if request.mode == "bm25":
            mode = "bm25"
        elif self._embeddings.available:
            query_vector = await self._embeddings.embed_query(request.query)
            mode = "hybrid" if request.mode == "auto" else cast(ResolvedSearchMode, request.mode)
        elif request.mode == "auto":
            mode = "bm25"
        else:
            raise EmbeddingUnavailableError(
                f"{request.mode} search requires PAPERFORGE_EMBEDDINGS__API_KEY"
            )

        return await asyncio.to_thread(
            self._client.search,
            request,
            mode=mode,
            query_vector=query_vector,
        )
