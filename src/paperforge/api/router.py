"""Top-level API router."""

from fastapi import APIRouter

from paperforge.api.routes.cache import router as cache_router
from paperforge.api.routes.feedback import router as feedback_router
from paperforge.api.routes.health import router as health_router
from paperforge.api.routes.hybrid_search import router as hybrid_search_router
from paperforge.api.routes.rag import router as rag_router
from paperforge.api.routes.search import router as search_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health_router)
api_router.include_router(hybrid_search_router)
api_router.include_router(search_router)
api_router.include_router(rag_router)
api_router.include_router(cache_router)
api_router.include_router(feedback_router)
