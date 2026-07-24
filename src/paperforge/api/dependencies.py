"""FastAPI dependency factories."""

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from paperforge.core.config import Settings, get_settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.redis import RedisClient
from paperforge.infrastructure.resources import Infrastructure
from paperforge.services.health import HealthService

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
