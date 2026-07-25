"""Week 6 exact-response cache diagnostics and invalidation."""

from fastapi import APIRouter

from paperforge.api.dependencies import RAGCacheDep, SettingsDep
from paperforge.schemas.cache import CacheInvalidationResponse, CacheStatsResponse
from paperforge.schemas.rag import RAGRequest

router = APIRouter(prefix="/cache", tags=["cache"])


@router.get("/stats", response_model=CacheStatsResponse)
async def cache_stats(cache: RAGCacheDep) -> CacheStatsResponse:
    return await cache.stats()


@router.post("/invalidate", response_model=CacheInvalidationResponse)
async def invalidate_cache(
    request: RAGRequest, cache: RAGCacheDep, settings: SettingsDep
) -> CacheInvalidationResponse:
    model = request.model or settings.rag.default_model
    key, deleted = await cache.invalidate(request, resolved_model=model)
    return CacheInvalidationResponse(deleted=deleted, cache_key=key)
