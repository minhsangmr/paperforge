"""FastAPI application factory and lifecycle."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from paperforge import __version__
from paperforge.api.router import api_router
from paperforge.core.config import Settings, get_settings
from paperforge.core.logging import configure_logging
from paperforge.infrastructure.resources import Infrastructure, build_infrastructure
from paperforge.middleware.request_id import RequestIDMiddleware

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    infrastructure: Infrastructure | None = None,
) -> FastAPI:
    """Create an application with injectable settings and infrastructure."""

    resolved_settings = settings or get_settings()
    configure_logging(resolved_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        resources = infrastructure or build_infrastructure(resolved_settings)
        application.state.infrastructure = resources
        logger.info(
            "application.started",
            extra={
                "service": resolved_settings.service_name,
                "version": __version__,
                "environment": resolved_settings.environment,
            },
        )
        try:
            yield
        finally:
            await resources.close()
            logger.info("application.stopped", extra={"service": resolved_settings.service_name})

    application = FastAPI(
        title="Paperforge API",
        description="Container-first academic paper RAG platform.",
        version=__version__,
        debug=resolved_settings.environment == "development",
        lifespan=lifespan,
    )
    application.add_middleware(RequestIDMiddleware)
    application.include_router(api_router)
    return application


app = create_app()
