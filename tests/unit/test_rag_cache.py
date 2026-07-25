"""Tests for parameter-aware Redis response caching."""

import asyncio
from typing import cast
from unittest.mock import MagicMock

from paperforge.core.config import RAGCacheSettings
from paperforge.infrastructure.redis import RedisClient
from paperforge.schemas.rag import RAGRequest, RAGResponse, RAGSource
from paperforge.services.cache.rag import RAGCache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.counters: dict[str, int] = {}

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        self.values[key] = value
        return ttl_seconds is not None

    def delete(self, key: str) -> int:
        return int(self.values.pop(key, None) is not None)

    def increment(self, key: str, amount: int = 1) -> int:
        self.counters[key] = self.counters.get(key, 0) + amount
        return self.counters[key]

    def get_many(self, keys: list[str]) -> list[str | None]:
        return [str(self.counters[key]) if key in self.counters else None for key in keys]


def _response() -> RAGResponse:
    return RAGResponse(
        query="What is RAG?",
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


def test_key_is_normalized_and_parameter_aware() -> None:
    cache = RAGCache(None, RAGCacheSettings())
    first = cache.build_key(
        RAGRequest(query=" What   is RAG? ", categories=["cs.IR", "cs.AI"]),
        resolved_model="llama3.2:1b",
    )
    same = cache.build_key(
        RAGRequest(query="What is RAG?", categories=["cs.AI", "cs.IR"]),
        resolved_model="llama3.2:1b",
    )
    different = cache.build_key(
        RAGRequest(query="What is RAG?", top_k=5, categories=["cs.AI", "cs.IR"]),
        resolved_model="llama3.2:1b",
    )
    assert first == same
    assert first != different


def test_store_lookup_invalidate_and_stats() -> None:
    redis = FakeRedis()
    cache = RAGCache(cast(RedisClient, redis), RAGCacheSettings(ttl_seconds=600))
    request = RAGRequest(query="What is RAG?")

    assert asyncio.run(cache.lookup(request, resolved_model="llama3.2:1b")).payload is None
    assert asyncio.run(cache.store(request, _response(), resolved_model="llama3.2:1b"))
    hit = asyncio.run(cache.lookup(request, resolved_model="llama3.2:1b"))
    assert hit.payload is not None
    assert hit.payload.answer == "Grounded answer [S1]"

    key, deleted = asyncio.run(cache.invalidate(request, resolved_model="llama3.2:1b"))
    assert deleted is True
    assert key.startswith("paperforge:rag-cache:v1:response:")
    stats = asyncio.run(cache.stats())
    assert stats.hits == 1
    assert stats.misses == 1
    assert stats.writes == 1
    assert stats.invalidations == 1
    assert stats.hit_rate == 0.5


def test_cache_degrades_when_redis_raises() -> None:
    redis = MagicMock()
    redis.get.side_effect = RuntimeError("offline")
    redis.increment.side_effect = RuntimeError("offline")
    cache = RAGCache(cast(RedisClient, redis), RAGCacheSettings())
    result = asyncio.run(cache.lookup(RAGRequest(query="Question"), resolved_model="model"))
    assert result.payload is None


def test_empty_source_response_is_not_cached_by_default() -> None:
    redis = FakeRedis()
    cache = RAGCache(cast(RedisClient, redis), RAGCacheSettings())
    response = _response().model_copy(update={"sources": [], "chunks_used": 0})
    stored = asyncio.run(
        cache.store(RAGRequest(query="Question"), response, resolved_model=response.model)
    )
    assert stored is False
    assert redis.values == {}


def test_cached_stream_chunks_are_deterministic() -> None:
    cache = RAGCache(None, RAGCacheSettings(stream_chunk_characters=16))
    chunks = cache.stream_chunks("abcdefghijklmnopqrstuvwxyz")
    assert chunks == ["abcdefghijklmnop", "qrstuvwxyz"]
