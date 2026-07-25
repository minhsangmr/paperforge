"""FastAPI dependency factories."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from paperforge.core.config import Settings, get_settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.redis import RedisClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.services.health import HealthService
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
