"""FastAPI dependency factories."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from paperforge.core.config import Settings, get_settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.redis import RedisClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.services.cache.rag import RAGCache
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.health import HealthService
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.observability.langfuse import LangfuseObservability
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.rag import RAGService
from paperforge.services.search import SearchService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_infrastructure(request: Request) -> Infrastructure:
    return cast(Infrastructure, request.app.state.infrastructure)


InfrastructureDep = Annotated[Infrastructure, Depends(get_infrastructure)]


def get_database(infrastructure: InfrastructureDep) -> Database:
    return infrastructure.database


DatabaseDep = Annotated[Database, Depends(get_database)]


def get_db_session(database: DatabaseDep) -> Iterator[Session]:
    with database.session() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db_session)]


def get_redis(infrastructure: InfrastructureDep) -> RedisClient | None:
    return infrastructure.redis


def get_health_service(settings: SettingsDep, infrastructure: InfrastructureDep) -> HealthService:
    return HealthService(
        settings=settings,
        database=infrastructure.database,
        opensearch=infrastructure.opensearch,
        redis=infrastructure.redis,
        ollama=infrastructure.ollama,
        langfuse=infrastructure.observability,
    )


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


def require_opensearch(infrastructure: InfrastructureDep) -> OpenSearchClient:
    if infrastructure.opensearch is None:
        raise HTTPException(status_code=503, detail="search service is disabled")
    return infrastructure.opensearch


OpenSearchDep = Annotated[OpenSearchClient, Depends(require_opensearch)]


def get_search_service(settings: SettingsDep, client: OpenSearchDep) -> SearchService:
    return SearchService(client, settings.opensearch)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


def require_hybrid_search(infrastructure: InfrastructureDep) -> HybridSearchClient:
    if infrastructure.hybrid_search is None:
        raise HTTPException(status_code=503, detail="hybrid search is disabled")
    return infrastructure.hybrid_search


def require_embeddings(infrastructure: InfrastructureDep) -> JinaEmbeddingsClient:
    if infrastructure.embeddings is None:
        raise HTTPException(status_code=503, detail="embedding service is disabled")
    return infrastructure.embeddings


HybridSearchClientDep = Annotated[HybridSearchClient, Depends(require_hybrid_search)]
EmbeddingsDep = Annotated[JinaEmbeddingsClient, Depends(require_embeddings)]


def get_hybrid_search_service(
    settings: SettingsDep, client: HybridSearchClientDep, embeddings: EmbeddingsDep
) -> HybridSearchService:
    return HybridSearchService(client, embeddings, settings.hybrid_search)


HybridSearchServiceDep = Annotated[HybridSearchService, Depends(get_hybrid_search_service)]


def require_ollama(infrastructure: InfrastructureDep) -> OllamaClient:
    if infrastructure.ollama is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama generation is disabled",
        )
    return infrastructure.ollama


OllamaDep = Annotated[OllamaClient, Depends(require_ollama)]


def get_rag_cache(settings: SettingsDep, infrastructure: InfrastructureDep) -> RAGCache:
    return RAGCache(infrastructure.redis, settings.rag_cache)


RAGCacheDep = Annotated[RAGCache, Depends(get_rag_cache)]


def get_observability(
    settings: SettingsDep, infrastructure: InfrastructureDep
) -> LangfuseObservability:
    return infrastructure.observability or LangfuseObservability(settings.langfuse)


ObservabilityDep = Annotated[LangfuseObservability, Depends(get_observability)]


def get_rag_service(
    settings: SettingsDep,
    retrieval: HybridSearchServiceDep,
    ollama: OllamaDep,
    cache: RAGCacheDep,
    observability: ObservabilityDep,
) -> RAGService:
    return RAGService(retrieval, ollama, settings.rag, cache, observability)


RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
