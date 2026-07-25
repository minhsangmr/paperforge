"""Unit tests for hybrid search mode resolution."""

from typing import cast

import pytest

from paperforge.core.config import HybridSearchSettings
from paperforge.exceptions import EmbeddingUnavailableError
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.schemas.hybrid_search import (
    HybridSearchRequest,
    HybridSearchResponse,
    ResolvedSearchMode,
)
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.hybrid_search import HybridSearchService


class FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[ResolvedSearchMode, list[float] | None]] = []

    def search(
        self,
        request: HybridSearchRequest,
        *,
        mode: ResolvedSearchMode,
        query_vector: list[float] | None,
    ) -> HybridSearchResponse:
        self.calls.append((mode, query_vector))
        return HybridSearchResponse(
            query=request.query,
            requested_mode=request.mode,
            search_mode=mode,
            embeddings_used=query_vector is not None,
            total=0,
            page=request.page,
            page_size=request.page_size,
            took_ms=1,
            hits=[],
        )


class FakeEmbeddings:
    def __init__(self, available: bool) -> None:
        self.available = available

    async def embed_query(self, query: str) -> list[float]:
        return [0.1, 0.2]


def _service(
    available: bool, settings: HybridSearchSettings | None = None
) -> tuple[HybridSearchService, FakeClient]:
    client = FakeClient()
    return (
        HybridSearchService(
            cast(HybridSearchClient, client),
            cast(JinaEmbeddingsClient, FakeEmbeddings(available)),
            settings or HybridSearchSettings(),
        ),
        client,
    )


@pytest.mark.asyncio
async def test_auto_uses_hybrid_when_available_and_bm25_without_key() -> None:
    service, _ = _service(True)
    response = await service.search(HybridSearchRequest(query="q", mode="auto"))
    assert response.search_mode == "hybrid"

    fallback, _ = _service(False)
    response = await fallback.search(HybridSearchRequest(query="q", mode="auto"))
    assert response.search_mode == "bm25"


@pytest.mark.asyncio
async def test_explicit_vector_requires_embeddings_and_validates_window() -> None:
    service, _ = _service(False)
    with pytest.raises(EmbeddingUnavailableError):
        await service.search(HybridSearchRequest(query="q", mode="vector"))

    limited, _ = _service(
        True,
        HybridSearchSettings(default_page_size=5, max_page_size=5),
    )
    with pytest.raises(ValueError, match="page_size"):
        await limited.search(HybridSearchRequest(query="q", page_size=6))


@pytest.mark.asyncio
async def test_bm25_does_not_require_embeddings_and_window_is_bounded() -> None:
    service, _ = _service(False, HybridSearchSettings(max_result_window=100))
    response = await service.search(HybridSearchRequest(query="q", mode="bm25"))
    assert response.search_mode == "bm25"

    with pytest.raises(ValueError, match="result window"):
        await service.search(HybridSearchRequest(query="q", mode="bm25", page=11, page_size=10))
