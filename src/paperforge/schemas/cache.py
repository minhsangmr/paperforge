"""Schemas for Week 6 exact-response caching."""

from pydantic import BaseModel, ConfigDict, Field

from paperforge.schemas.hybrid_search import ResolvedSearchMode
from paperforge.schemas.rag import OllamaUsage, RAGSource


class CachedRAGPayload(BaseModel):
    """Stable payload persisted in Redis without request-specific trace metadata."""

    model_config = ConfigDict(frozen=True)

    query: str
    answer: str
    sources: list[RAGSource]
    chunks_used: int = Field(ge=0)
    search_mode: ResolvedSearchMode
    model: str
    usage: OllamaUsage = Field(default_factory=OllamaUsage)


class CacheStatsResponse(BaseModel):
    """Aggregated cache counters stored in Redis."""

    model_config = ConfigDict(frozen=True)

    enabled: bool
    namespace: str
    ttl_seconds: int = Field(ge=1)
    hits: int = Field(default=0, ge=0)
    misses: int = Field(default=0, ge=0)
    writes: int = Field(default=0, ge=0)
    errors: int = Field(default=0, ge=0)
    invalidations: int = Field(default=0, ge=0)
    hit_rate: float = Field(default=0.0, ge=0, le=1)


class CacheInvalidationResponse(BaseModel):
    """Result of deleting one exact-match cache entry."""

    model_config = ConfigDict(frozen=True)

    deleted: bool
    cache_key: str
