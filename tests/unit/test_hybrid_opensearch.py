"""Unit tests for the Week 4 OpenSearch adapter and mappings."""

from datetime import UTC, datetime
from typing import Any, cast

import pytest

from paperforge.core.config import (
    EmbeddingSettings,
    HybridSearchSettings,
    OpenSearchSettings,
)
from paperforge.exceptions import SearchIndexSchemaError
from paperforge.infrastructure.hybrid_search import (
    HybridSearchClient,
    build_hybrid_index,
    build_rrf_pipeline,
)
from paperforge.schemas.hybrid_search import HybridChunkDocument, HybridSearchRequest


class FakeIndices:
    def __init__(self, parent: "FakeOpenSearch") -> None:
        self.parent = parent

    def exists(self, *, index: str) -> bool:
        return self.parent.exists

    def create(self, *, index: str, body: dict[str, Any]) -> None:
        self.parent.exists = True
        self.parent.created = (index, body)

    def delete(self, *, index: str) -> None:
        self.parent.exists = False

    def get_mapping(self, *, index: str) -> dict[str, Any]:
        return {index: {"mappings": {"_meta": {"paperforge_schema_version": self.parent.version}}}}

    def stats(self, *, index: str) -> dict[str, Any]:
        return {
            "indices": {
                index: {
                    "total": {
                        "docs": {"count": 2, "deleted": 1},
                        "store": {"size_in_bytes": 42},
                    }
                }
            }
        }


class FakeTransport:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any]]] = []

    def perform_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
    ) -> None:
        self.requests.append((method, path, body or {}))


class FakeOpenSearch:
    def __init__(self, *, exists: bool = False, version: int = 1) -> None:
        self.exists = exists
        self.version = version
        self.indices = FakeIndices(self)
        self.transport = FakeTransport()
        self.created: tuple[str, dict[str, Any]] | None = None
        self.search_kwargs: dict[str, object] | None = None
        self.bulk_body: list[dict[str, Any]] = []
        self.closed = False

    def bulk(self, **kwargs: object) -> dict[str, Any]:
        self.bulk_body = cast(list[dict[str, Any]], kwargs["body"])
        return {"items": [{"index": {"status": 201}}]}

    def delete_by_query(self, **_: object) -> dict[str, Any]:
        return {"deleted": 2}

    def search(self, **kwargs: object) -> dict[str, Any]:
        self.search_kwargs = kwargs
        body = kwargs.get("body")
        if isinstance(body, dict) and body.get("size") == 0:
            return {"aggregations": {"papers": {"value": 1}}}
        return {
            "took": 3,
            "hits": {
                "total": {"value": 1},
                "hits": [
                    {
                        "_score": 0.8,
                        "_source": {
                            "chunk_id": "c1",
                            "chunk_index": 0,
                            "arxiv_id": "a1",
                            "title": "T",
                            "authors": ["A"],
                            "abstract": "B",
                            "categories": ["cs.AI"],
                            "published_date": "2026-01-01T00:00:00Z",
                            "pdf_url": "https://example.test/a.pdf",
                            "section_title": "Intro",
                            "chunk_text": "text",
                        },
                    }
                ],
            },
        }

    def count(self, **_: object) -> dict[str, Any]:
        return {"count": 1}

    def close(self) -> None:
        self.closed = True


def _client(fake: FakeOpenSearch) -> HybridSearchClient:
    return HybridSearchClient(
        OpenSearchSettings(),
        HybridSearchSettings(),
        EmbeddingSettings(dimensions=4),
        client=fake,
    )


def test_mapping_and_rrf_pipeline() -> None:
    settings = HybridSearchSettings(bm25_weight=0.6, vector_weight=0.4)
    mapping = build_hybrid_index(settings, EmbeddingSettings(dimensions=4))
    mappings = cast(dict[str, Any], mapping["mappings"])
    properties = cast(dict[str, Any], mappings["properties"])
    vector = cast(dict[str, Any], properties[settings.embedding_field])
    index_settings = cast(dict[str, Any], mapping["settings"])
    assert index_settings["index.knn"] is True
    assert vector["dimension"] == 4
    method = cast(dict[str, Any], vector["method"])
    assert method["engine"] == "lucene"
    pipeline = build_rrf_pipeline(settings)
    processors = cast(list[dict[str, Any]], pipeline["phase_results_processors"])
    ranker = cast(dict[str, Any], processors[0]["score-ranker-processor"])
    combination = cast(dict[str, Any], ranker["combination"])
    assert combination == {
        "technique": "rrf",
        "rank_constant": settings.rrf_rank_constant,
    }


def test_ensure_index_validates_schema_and_creates_pipeline() -> None:
    fake = FakeOpenSearch()
    client = _client(fake)
    assert client.ensure_index() is True
    assert fake.created is not None
    assert fake.transport.requests[0][0:2] == (
        "PUT",
        "/_search/pipeline/paperforge-hybrid-rrf-v1",
    )

    incompatible = _client(FakeOpenSearch(exists=True, version=9))
    with pytest.raises(SearchIndexSchemaError):
        incompatible.ensure_index()


def test_bulk_search_stats_and_delete() -> None:
    fake = FakeOpenSearch(exists=True)
    client = _client(fake)
    document = HybridChunkDocument(
        chunk_id="c1",
        chunk_index=0,
        paper_id="p1",
        arxiv_id="a1",
        title="T",
        authors=["A"],
        abstract="B",
        categories=["cs.AI"],
        published_date=datetime(2026, 1, 1, tzinfo=UTC),
        pdf_url="https://example.test/a.pdf",
        section_title="Intro",
        section_level=1,
        chunk_text="text",
        chunk_word_count=1,
        has_embedding=True,
        embedding_model="m",
        embedding=[0.1, 0.2, 0.3, 0.4],
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    result = client.bulk_index([document], refresh=True)
    assert result.indexed == 1
    assert fake.bulk_body[0]["index"]["_id"] == "c1"
    assert client.delete_stale_paper_chunks("a1", keep_chunk_ids=["c1"]) == 2

    response = client.search(
        HybridSearchRequest(query="q", mode="hybrid"),
        mode="hybrid",
        query_vector=[0.1] * 4,
    )
    assert response.search_mode == "hybrid"
    assert response.hits[0].chunk_id == "c1"
    assert fake.search_kwargs is not None
    params = cast(dict[str, str], fake.search_kwargs["params"])
    assert params["search_pipeline"] == client.settings.search_pipeline

    stats = client.stats()
    assert stats.document_count == 2
    assert stats.embedded_document_count == 1
    assert stats.unique_paper_count == 1
    client.delete_index()
    client.delete_pipeline()
    assert fake.exists is False
    assert fake.transport.requests[-1][0:2] == (
        "DELETE",
        "/_search/pipeline/paperforge-hybrid-rrf-v1",
    )
    client.close()
    assert fake.closed is True


def test_empty_index_operations_are_safe() -> None:
    fake = FakeOpenSearch(exists=False)
    client = _client(fake)
    client.delete_index()
    assert client.delete_stale_paper_chunks("missing", keep_chunk_ids=[]) == 0
    assert client.bulk_index([]).attempted == 0
    assert client.stats().exists is False
