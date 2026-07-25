"""Exact-match Redis cache for successful RAG responses."""

import asyncio
import hashlib
import json
import logging
import unicodedata
from dataclasses import dataclass

from paperforge.core.config import RAGCacheSettings
from paperforge.infrastructure.redis import RedisClient
from paperforge.schemas.cache import CachedRAGPayload, CacheStatsResponse
from paperforge.schemas.rag import RAGRequest, RAGResponse

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CacheLookup:
    """One cache lookup result and its deterministic key."""

    key: str
    payload: CachedRAGPayload | None


class RAGCache:
    """Parameter-aware response cache that degrades safely when Redis is unavailable."""

    _COUNTERS = ("hits", "misses", "writes", "errors", "invalidations")

    def __init__(
        self,
        redis: RedisClient | None,
        settings: RAGCacheSettings,
    ) -> None:
        self._redis = redis
        self._settings = settings

    @property
    def enabled(self) -> bool:
        return self._settings.enabled and self._redis is not None

    def build_key(self, request: RAGRequest, *, resolved_model: str) -> str:
        """Build a stable key from every parameter that can change the answer."""

        canonical = {
            "schema": self._settings.response_schema_version,
            "query": self._normalize_query(request.query),
            "model": resolved_model.strip(),
            "top_k": request.top_k,
            "use_hybrid": request.use_hybrid,
            "categories": sorted(set(request.categories)),
        }
        digest = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return f"{self._settings.namespace}:response:{digest}"

    async def lookup(self, request: RAGRequest, *, resolved_model: str) -> CacheLookup:
        """Read and validate one cached response."""

        key = self.build_key(request, resolved_model=resolved_model)
        if not self.enabled:
            return CacheLookup(key=key, payload=None)
        assert self._redis is not None
        try:
            raw = await asyncio.to_thread(self._redis.get, key)
            if raw is None:
                await self._increment("misses")
                return CacheLookup(key=key, payload=None)
            payload = CachedRAGPayload.model_validate_json(raw)
            await self._increment("hits")
            return CacheLookup(key=key, payload=payload)
        except Exception:
            logger.exception("rag_cache.lookup_failed", extra={"cache_key": key})
            await self._increment("errors")
            return CacheLookup(key=key, payload=None)

    async def store(
        self,
        request: RAGRequest,
        response: RAGResponse,
        *,
        resolved_model: str,
    ) -> bool:
        """Cache only a fully completed response."""

        if not self.enabled:
            return False
        if not response.answer.strip():
            return False
        if not response.sources and not self._settings.cache_empty_answers:
            return False
        assert self._redis is not None
        key = self.build_key(request, resolved_model=resolved_model)
        payload = CachedRAGPayload(
            query=response.query,
            answer=response.answer,
            sources=response.sources,
            chunks_used=response.chunks_used,
            search_mode=response.search_mode,
            model=response.model,
            usage=response.usage,
        )
        try:
            stored = await asyncio.to_thread(
                self._redis.set,
                key,
                payload.model_dump_json(),
                self._settings.ttl_seconds,
            )
            if stored:
                await self._increment("writes")
            return stored
        except Exception:
            logger.exception("rag_cache.store_failed", extra={"cache_key": key})
            await self._increment("errors")
            return False

    async def invalidate(self, request: RAGRequest, *, resolved_model: str) -> tuple[str, bool]:
        """Delete one exact-match cache entry."""

        key = self.build_key(request, resolved_model=resolved_model)
        if not self.enabled:
            return key, False
        assert self._redis is not None
        try:
            deleted = bool(await asyncio.to_thread(self._redis.delete, key))
            if deleted:
                await self._increment("invalidations")
            return key, deleted
        except Exception:
            logger.exception("rag_cache.invalidate_failed", extra={"cache_key": key})
            await self._increment("errors")
            return key, False

    async def stats(self) -> CacheStatsResponse:
        """Return counters without scanning the Redis keyspace."""

        values = {counter: 0 for counter in self._COUNTERS}
        if self.enabled:
            assert self._redis is not None
            try:
                keys = [self._counter_key(counter) for counter in self._COUNTERS]
                raw_values = await asyncio.to_thread(self._redis.get_many, keys)
                values = {
                    counter: int(raw or 0)
                    for counter, raw in zip(self._COUNTERS, raw_values, strict=True)
                }
            except Exception:
                logger.exception("rag_cache.stats_failed")
                values["errors"] += 1
        attempts = values["hits"] + values["misses"]
        hit_rate = values["hits"] / attempts if attempts else 0.0
        return CacheStatsResponse(
            enabled=self.enabled,
            namespace=self._settings.namespace,
            ttl_seconds=self._settings.ttl_seconds,
            hits=values["hits"],
            misses=values["misses"],
            writes=values["writes"],
            errors=values["errors"],
            invalidations=values["invalidations"],
            hit_rate=hit_rate,
        )

    def stream_chunks(self, answer: str) -> list[str]:
        """Split a cached answer into deterministic SSE-sized chunks."""

        size = self._settings.stream_chunk_characters
        return [answer[index : index + size] for index in range(0, len(answer), size)]

    async def _increment(self, counter: str) -> None:
        if not self.enabled:
            return
        assert self._redis is not None
        try:
            await asyncio.to_thread(self._redis.increment, self._counter_key(counter))
        except Exception:
            logger.warning("rag_cache.counter_failed", extra={"counter": counter})

    def _counter_key(self, counter: str) -> str:
        return f"{self._settings.namespace}:stats:{counter}"

    @staticmethod
    def _normalize_query(value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        return " ".join(normalized.split())
