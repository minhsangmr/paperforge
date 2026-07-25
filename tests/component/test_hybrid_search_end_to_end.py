"""End-to-end PostgreSQL to OpenSearch RRF hybrid component test."""

from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import delete

from paperforge.core.config import (
    ChunkingSettings,
    EmbeddingSettings,
    HybridSearchSettings,
    get_settings,
)
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.hybrid_search import HybridSearchRequest
from paperforge.services.chunking import SectionAwareChunker
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.hybrid_indexing import HybridIndexingService
from paperforge.services.hybrid_search import HybridSearchService

pytestmark = pytest.mark.component


class DeterministicEmbeddings:
    """Avoid external API calls while exercising the real vector index."""

    def __init__(self, settings: EmbeddingSettings) -> None:
        self.settings = settings
        self.available = True

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    async def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0, 0.0, 0.0]


@pytest.mark.asyncio
async def test_postgres_to_rrf_hybrid_search_round_trip() -> None:
    settings = get_settings()
    suffix = uuid4().hex[:10]
    arxiv_id = f"hybrid-component.{suffix}"
    embedding_settings = EmbeddingSettings(
        api_key=SecretStr("component-placeholder"),
        model="component-embedding",
        dimensions=4,
    )
    hybrid_settings = HybridSearchSettings(
        index_name=f"paperforge-hybrid-component-{suffix}",
        search_pipeline=f"paperforge-hybrid-component-{suffix}",
        bulk_batch_size=10,
    )
    database = Database(settings.database)
    client = HybridSearchClient(
        settings.opensearch,
        hybrid_settings,
        embedding_settings,
    )
    embeddings = cast(JinaEmbeddingsClient, DeterministicEmbeddings(embedding_settings))
    try:
        with database.session() as session:
            session.add(
                Paper(
                    arxiv_id=arxiv_id,
                    title="Semantic and Lexical Retrieval",
                    authors=["Paperforge Test"],
                    abstract="A deterministic hybrid-search component test.",
                    categories=["cs.IR"],
                    published_date=datetime.now(UTC),
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                    raw_text=(
                        "semantic vector retrieval and lexical keyword ranking "
                        "work together through reciprocal rank fusion"
                    ),
                    sections=[
                        {
                            "title": "Retrieval",
                            "level": 1,
                            "content": (
                                "semantic vector retrieval and lexical keyword ranking "
                                "work together through reciprocal rank fusion"
                            ),
                        }
                    ],
                    pdf_processed=True,
                )
            )

        with database.session() as session:
            report = await HybridIndexingService(
                PaperRepository(session),
                SectionAwareChunker(
                    ChunkingSettings(chunk_size_words=20, overlap_words=4, min_chunk_words=3)
                ),
                embeddings,
                client,
            ).run(batch_size=10, refresh=True, embed=True)
        assert report.failed == 0
        assert report.chunks_indexed > 0

        response = await HybridSearchService(client, embeddings, hybrid_settings).search(
            HybridSearchRequest(
                query="semantic retrieval",
                mode="hybrid",
                categories=["cs.IR"],
                page_size=10,
            )
        )
        assert response.search_mode == "hybrid"
        assert response.embeddings_used is True
        assert any(hit.arxiv_id == arxiv_id for hit in response.hits)
    finally:
        client.delete_index()
        client.delete_pipeline()
        client.close()
        with database.session() as session:
            session.execute(delete(Paper).where(Paper.arxiv_id == arxiv_id))
        database.close()
