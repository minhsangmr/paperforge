"""Unit tests for PostgreSQL-to-chunk-index synchronization."""

from collections.abc import Iterator
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest

from paperforge.core.config import (
    ChunkingSettings,
    EmbeddingSettings,
    HybridSearchSettings,
)
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.hybrid_search import (
    HybridBulkIndexResult,
    HybridChunkDocument,
)
from paperforge.services.chunking import SectionAwareChunker
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.hybrid_indexing import HybridIndexingService


class FakeRepository:
    def __init__(self, papers: list[Paper]) -> None:
        self.papers = papers

    def iter_for_search_index(self, **_: object) -> Iterator[list[Paper]]:
        yield self.papers


class FakeEmbeddings:
    def __init__(self) -> None:
        self.settings = EmbeddingSettings(model="model", dimensions=3)

    async def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 2.0, 3.0] for _ in texts]


class FakeClient:
    def __init__(self) -> None:
        self.settings = HybridSearchSettings(index_name="hybrid")
        self.deleted: list[str] = []
        self.documents: list[HybridChunkDocument] = []
        self.rebuilt = False
        self.ensured = False

    def ensure_index(self) -> bool:
        self.ensured = True
        return True

    def recreate_index(self) -> None:
        self.rebuilt = True

    def delete_stale_paper_chunks(self, arxiv_id: str, *, keep_chunk_ids: list[str]) -> int:
        self.deleted.append(arxiv_id)
        assert keep_chunk_ids
        return 0

    def bulk_index(
        self, documents: list[HybridChunkDocument], *, refresh: bool
    ) -> HybridBulkIndexResult:
        self.documents.extend(documents)
        return HybridBulkIndexResult(attempted=len(documents), indexed=len(documents), failed=0)


def _paper(raw_text: str = "one two three four five six") -> Paper:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return cast(
        Paper,
        SimpleNamespace(
            id=uuid4(),
            arxiv_id="2601.00001",
            title="Paper",
            authors=["Author"],
            abstract="abstract words here",
            categories=["cs.AI"],
            published_date=now,
            pdf_url="https://example.test/p.pdf",
            raw_text=raw_text,
            sections=[{"title": "Intro", "content": raw_text, "level": 1}],
            updated_at=now,
        ),
    )


def _service(client: FakeClient, papers: list[Paper]) -> HybridIndexingService:
    return HybridIndexingService(
        cast(PaperRepository, FakeRepository(papers)),
        SectionAwareChunker(
            ChunkingSettings(chunk_size_words=5, overlap_words=1, min_chunk_words=2)
        ),
        cast(JinaEmbeddingsClient, FakeEmbeddings()),
        cast(HybridSearchClient, client),
    )


@pytest.mark.asyncio
async def test_hybrid_indexing_replaces_chunks_with_embeddings() -> None:
    client = FakeClient()
    report = await _service(client, [_paper()]).run(
        batch_size=10, rebuild=True, refresh=True, embed=True
    )
    assert client.rebuilt is True
    assert client.deleted == ["2601.00001"]
    assert report.papers_indexed == 1
    assert report.chunks_indexed == len(client.documents)
    assert all(document.has_embedding for document in client.documents)


@pytest.mark.asyncio
async def test_hybrid_indexing_supports_text_only() -> None:
    client = FakeClient()
    service = HybridIndexingService(
        cast(PaperRepository, FakeRepository([_paper(""), _paper("one two three")])),
        SectionAwareChunker(
            ChunkingSettings(chunk_size_words=10, overlap_words=2, min_chunk_words=2)
        ),
        cast(JinaEmbeddingsClient, FakeEmbeddings()),
        cast(HybridSearchClient, client),
    )
    report = await service.run(batch_size=10, embed=False)
    assert client.ensured is True
    assert report.papers_skipped == 0
    assert all(not document.has_embedding for document in client.documents)
