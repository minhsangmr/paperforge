"""Infrastructure resource factory and lifecycle container."""

from dataclasses import dataclass

from paperforge.core.config import Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.infrastructure.ollama import OllamaClient
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.redis import RedisClient
from paperforge.services.embeddings.jina import JinaEmbeddingsClient


@dataclass(slots=True)
class Infrastructure:
    """Process-owned adapters placed on FastAPI application state."""

    database: Database
    opensearch: OpenSearchClient | None
    redis: RedisClient | None
    ollama: OllamaClient | None
    hybrid_search: HybridSearchClient | None = None
    embeddings: JinaEmbeddingsClient | None = None

    async def close(self) -> None:
        """Release resources in reverse dependency order."""

        if self.embeddings is not None:
            await self.embeddings.close()
        if self.hybrid_search is not None:
            self.hybrid_search.close()
        if self.ollama is not None:
            await self.ollama.close()
        if self.redis is not None:
            self.redis.close()
        if self.opensearch is not None:
            self.opensearch.close()
        self.database.close()


def build_infrastructure(settings: Settings) -> Infrastructure:
    """Build adapters without performing network I/O."""

    return Infrastructure(
        database=Database(settings.database),
        opensearch=OpenSearchClient(settings.opensearch) if settings.opensearch.enabled else None,
        redis=RedisClient(settings.redis) if settings.redis.enabled else None,
        ollama=OllamaClient(settings.ollama) if settings.ollama.enabled else None,
        hybrid_search=(
            HybridSearchClient(settings.opensearch, settings.hybrid_search, settings.embeddings)
            if settings.opensearch.enabled and settings.hybrid_search.enabled
            else None
        ),
        embeddings=(
            JinaEmbeddingsClient(settings.embeddings) if settings.embeddings.enabled else None
        ),
    )
