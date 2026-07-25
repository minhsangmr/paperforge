"""Week 6 cache behavior around the RAG orchestrator."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from paperforge.core.config import LangfuseSettings, RAGSettings
from paperforge.schemas.cache import CachedRAGPayload
from paperforge.schemas.rag import OllamaUsage, RAGRequest, RAGSource, RAGStreamEvent
from paperforge.services.cache.rag import CacheLookup, RAGCache
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.observability.langfuse import LangfuseObservability
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.rag import RAGService


def _payload() -> CachedRAGPayload:
    return CachedRAGPayload(
        query="What is RAG?",
        answer="Cached answer [S1]",
        sources=[
            RAGSource(
                citation="S1",
                arxiv_id="2607.00001",
                title="RAG",
                pdf_url="https://arxiv.org/pdf/2607.00001.pdf",
                section_title="Methods",
                chunk_id="chunk-1",
            )
        ],
        chunks_used=1,
        search_mode="bm25",
        model="llama3.2:1b",
        usage=OllamaUsage(prompt_tokens=4, completion_tokens=3),
    )


def _service(cache: RAGCache) -> tuple[RAGService, MagicMock, MagicMock]:
    retrieval = MagicMock()
    retrieval.search = AsyncMock()
    ollama = MagicMock()
    ollama.generate = AsyncMock()
    observability = LangfuseObservability(LangfuseSettings(enabled=False))
    service = RAGService(
        cast(HybridSearchService, retrieval),
        cast(OllamaClient, ollama),
        RAGSettings(),
        cache,
        observability,
    )
    return service, retrieval, ollama


def test_complete_cache_hit_skips_retrieval_and_generation() -> None:
    cache = MagicMock(spec=RAGCache)
    cache.build_key.return_value = "cache-key"
    cache.lookup = AsyncMock(return_value=CacheLookup("cache-key", _payload()))
    service, retrieval, ollama = _service(cast(RAGCache, cache))

    response = asyncio.run(service.answer(RAGRequest(query="What is RAG?")))

    assert response.cache_hit is True
    assert response.answer == "Cached answer [S1]"
    retrieval.search.assert_not_awaited()
    ollama.generate.assert_not_awaited()


def test_stream_cache_hit_replays_sse_without_generation() -> None:
    cache = MagicMock(spec=RAGCache)
    cache.lookup = AsyncMock(return_value=CacheLookup("cache-key", _payload()))
    cache.stream_chunks.return_value = ["Cached ", "answer [S1]"]
    service, retrieval, ollama = _service(cast(RAGCache, cache))

    async def collect() -> list[RAGStreamEvent]:
        return [event async for event in service.stream(RAGRequest(query="What is RAG?"))]

    events = asyncio.run(collect())
    assert [event.event for event in events] == ["metadata", "token", "token", "done"]
    assert events[0].data["cache_hit"] is True
    assert events[-1].data["cache_hit"] is True
    retrieval.search.assert_not_awaited()
    ollama.generate_stream.assert_not_called()
