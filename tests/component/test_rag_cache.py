"""Week 6 response-cache component test against real Redis."""

import asyncio
from uuid import uuid4

import pytest

from paperforge.core.config import RAGCacheSettings, get_settings
from paperforge.infrastructure.redis import RedisClient
from paperforge.schemas.rag import RAGRequest, RAGResponse, RAGSource
from paperforge.services.cache.rag import RAGCache

pytestmark = pytest.mark.component


def test_rag_response_cache_round_trip() -> None:
    redis = RedisClient(get_settings().redis)
    namespace = f"paperforge:test-cache:{uuid4()}"
    cache = RAGCache(redis, RAGCacheSettings(namespace=namespace, ttl_seconds=60))
    request = RAGRequest(query="What is RAG?")
    response = RAGResponse(
        query=request.query,
        answer="Grounded answer [S1]",
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
    )
    try:
        assert asyncio.run(cache.store(request, response, resolved_model=response.model))
        lookup = asyncio.run(cache.lookup(request, resolved_model=response.model))
        assert lookup.payload is not None
        assert lookup.payload.answer == response.answer
        assert 0 < redis.ttl(lookup.key) <= 60
    finally:
        key = cache.build_key(request, resolved_model=response.model)
        redis.delete(key)
        redis.close()
