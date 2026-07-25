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
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.health import HealthService
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.rag import RAGService
from paperforge.services.search import SearchService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_infrastructure(request: Request) -> Infrastructure:
    """Read process-owned infrastructure from application state."""

    return cast(Infrastructure, request.app.state.infrastructure)


InfrastructureDep = Annotated[Infrastructure, Depends(get_infrastructure)]


def get_database(infrastructure: InfrastructureDep) -> Database:
    """Return the PostgreSQL adapter."""

    return infrastructure.database


DatabaseDep = Annotated[Database, Depends(get_database)]


def get_db_session(database: DatabaseDep) -> Iterator[Session]:
    """Yield one transactional SQLAlchemy session per request."""

    with database.session() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_db_session)]


def get_opensearch(infrastructure: InfrastructureDep) -> OpenSearchClient | None:
    """Return the optional OpenSearch adapter."""

    return infrastructure.opensearch


def require_opensearch(infrastructure: InfrastructureDep) -> OpenSearchClient:
    """Return OpenSearch or fail with a stable service-unavailable response."""

    if infrastructure.opensearch is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="search service is disabled",
        )
    return infrastructure.opensearch


OpenSearchDep = Annotated[OpenSearchClient, Depends(require_opensearch)]


def get_redis(infrastructure: InfrastructureDep) -> RedisClient | None:
    """Return the optional Redis adapter."""

    return infrastructure.redis


def get_health_service(
    settings: SettingsDep,
    infrastructure: InfrastructureDep,
) -> HealthService:
    """Build the readiness aggregation service."""

    return HealthService(
        settings=settings,
        database=infrastructure.database,
        opensearch=infrastructure.opensearch,
        redis=infrastructure.redis,
        ollama=infrastructure.ollama,
    )


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


def get_search_service(
    settings: SettingsDep,
    client: OpenSearchDep,
) -> SearchService:
    """Build a request-scoped search application service."""

    return SearchService(client, settings.opensearch)


SearchServiceDep = Annotated[SearchService, Depends(get_search_service)]


def require_hybrid_search(infrastructure: InfrastructureDep) -> HybridSearchClient:
    """Return the Week 4 chunk index adapter or fail with HTTP 503."""

    if infrastructure.hybrid_search is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="hybrid search is disabled",
        )
    return infrastructure.hybrid_search


def require_embeddings(infrastructure: InfrastructureDep) -> JinaEmbeddingsClient:
    """Return the embedding adapter, even when it is not API-key configured."""

    if infrastructure.embeddings is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="embedding service is disabled",
        )
    return infrastructure.embeddings


HybridSearchClientDep = Annotated[HybridSearchClient, Depends(require_hybrid_search)]
EmbeddingsDep = Annotated[JinaEmbeddingsClient, Depends(require_embeddings)]


def get_hybrid_search_service(
    settings: SettingsDep,
    client: HybridSearchClientDep,
    embeddings: EmbeddingsDep,
) -> HybridSearchService:
    """Build the unified retrieval application service."""

    return HybridSearchService(client, embeddings, settings.hybrid_search)


HybridSearchServiceDep = Annotated[HybridSearchService, Depends(get_hybrid_search_service)]


def require_ollama(infrastructure: InfrastructureDep) -> OllamaClient:
    """Return Ollama or fail with a stable service-unavailable response."""

    if infrastructure.ollama is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Ollama generation is disabled",
        )
    return infrastructure.ollama


OllamaDep = Annotated[OllamaClient, Depends(require_ollama)]


def get_rag_service(
    settings: SettingsDep,
    retrieval: HybridSearchServiceDep,
    ollama: OllamaDep,
) -> RAGService:
    """Build the Week 5 grounded-generation service."""

    return RAGService(retrieval, ollama, settings.rag)


RAGServiceDep = Annotated[RAGService, Depends(get_rag_service)]
