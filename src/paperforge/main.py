"""FastAPI application factory."""

from fastapi import FastAPI

from paperforge import __version__
from paperforge.api.router import api_router
from paperforge.core.config import get_settings


def create_app() -> FastAPI:
    """Create and configure the Paperforge API."""

    settings = get_settings()
    application = FastAPI(
        title="Paperforge API",
        description="Container-first academic paper RAG platform.",
        version=__version__,
        debug=settings.environment == "development",
    )
    application.include_router(api_router)
    return application


app = create_app()
