"""Versioned OpenSearch chunk index and RRF hybrid-search adapter."""

from typing import Any, cast
from urllib.parse import urlparse

from opensearchpy import OpenSearch

from paperforge.core.config import EmbeddingSettings, HybridSearchSettings, OpenSearchSettings
from paperforge.exceptions import SearchIndexSchemaError
from paperforge.schemas.hybrid_search import (
    HybridBulkIndexResult,
    HybridChunkDocument,
    HybridIndexStats,
    HybridSearchHit,
    HybridSearchRequest,
    HybridSearchResponse,
    ResolvedSearchMode,
)
from paperforge.services.hybrid_query import build_hybrid_search_query


def build_hybrid_index(
    settings: HybridSearchSettings,
    embeddings: EmbeddingSettings,
) -> dict[str, Any]:
    """Return the immutable Week 4 chunk-level hybrid index definition."""

    return {
        "settings": {
            "index.knn": True,
            "number_of_shards": 1,
            "number_of_replicas": 0,
            "index.max_result_window": settings.max_result_window,
            "analysis": {
                "normalizer": {
                    "paperforge_lowercase": {
                        "type": "custom",
                        "filter": ["lowercase", "asciifolding"],
                    }
                },
                "filter": {
                    "paperforge_english_stemmer": {
                        "type": "stemmer",
                        "language": "english",
                    }
                },
                "analyzer": {
                    "paperforge_english": {
                        "type": "custom",
                        "tokenizer": "standard",
                        "filter": [
                            "lowercase",
                            "asciifolding",
                            "paperforge_english_stemmer",
                        ],
                    }
                },
            },
            "similarity": {"paperforge_bm25": {"type": "BM25", "k1": 1.2, "b": 0.75}},
        },
        "mappings": {
            "dynamic": "strict",
            "_meta": {
                "paperforge_schema_version": settings.schema_version,
                "purpose": "week4-chunk-level-hybrid",
                "embedding_model": embeddings.model,
                "embedding_dimensions": embeddings.dimensions,
            },
            "properties": {
                "chunk_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "paper_id": {"type": "keyword"},
                "arxiv_id": {
                    "type": "keyword",
                    "normalizer": "paperforge_lowercase",
                },
                "title": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                },
                "authors": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                },
                "abstract": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                },
                "categories": {"type": "keyword"},
                "published_date": {"type": "date"},
                "pdf_url": {"type": "keyword", "index": False},
                "section_title": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "fields": {
                        "raw": {
                            "type": "keyword",
                            "normalizer": "paperforge_lowercase",
                            "ignore_above": 512,
                        }
                    },
                },
                "section_level": {"type": "integer"},
                "chunk_text": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                },
                "chunk_word_count": {"type": "integer"},
                "has_embedding": {"type": "boolean"},
                "embedding_model": {"type": "keyword"},
                settings.embedding_field: {
                    "type": "knn_vector",
                    "dimension": embeddings.dimensions,
                    "method": {
                        "name": "hnsw",
                        "engine": "lucene",
                        "space_type": "cosinesimil",
                        "parameters": {
                            "m": settings.hnsw_m,
                            "ef_construction": settings.hnsw_ef_construction,
                        },
                    },
                },
                "updated_at": {"type": "date"},
            },
        },
    }


def build_rrf_pipeline(settings: HybridSearchSettings) -> dict[str, Any]:
    """Return the OpenSearch 2.19 score-ranker pipeline definition."""

    return {
        "description": "Paperforge Week 4 reciprocal-rank-fusion pipeline",
        "phase_results_processors": [
            {
                "score-ranker-processor": {
                    "combination": {
                        "technique": "rrf",
                        "rank_constant": settings.rrf_rank_constant,
                    }
                }
            }
        ],
    }


class HybridSearchClient:
    """Typed adapter for the chunk-level vector index and unified retrieval."""

    def __init__(
        self,
        opensearch: OpenSearchSettings,
        settings: HybridSearchSettings,
        embeddings: EmbeddingSettings,
        client: Any | None = None,
    ) -> None:
        self.opensearch = opensearch
        self.settings = settings
        self.embeddings = embeddings
        self._client: Any = client or self._build_client(opensearch)

    @staticmethod
    def _build_client(settings: OpenSearchSettings) -> Any:
        parsed = urlparse(settings.url)
        if parsed.hostname is None:
            raise ValueError("OpenSearch URL must include a hostname")
        auth = None
        if parsed.username is not None:
            auth = (parsed.username, parsed.password or "")
        return OpenSearch(
            hosts=[
                {
                    "host": parsed.hostname,
                    "port": parsed.port or (443 if parsed.scheme == "https" else 9200),
                    "scheme": parsed.scheme or "http",
                }
            ],
            http_auth=auth,
            use_ssl=parsed.scheme == "https",
            verify_certs=parsed.scheme == "https",
            timeout=settings.timeout_seconds,
        )

    def ensure_index(self) -> bool:
        """Create the hybrid index once and reject incompatible mappings."""

        if bool(self._client.indices.exists(index=self.settings.index_name)):
            self._validate_schema()
            self.ensure_pipeline()
            return False
        try:
            self._client.indices.create(
                index=self.settings.index_name,
                body=build_hybrid_index(self.settings, self.embeddings),
            )
        except Exception as exc:
            if "resource_already_exists_exception" not in str(exc):
                raise
            self._validate_schema()
            self.ensure_pipeline()
            return False
        self.ensure_pipeline()
        return True

    def recreate_index(self) -> None:
        """Recreate only the derived Week 4 chunk index and RRF pipeline."""

        if bool(self._client.indices.exists(index=self.settings.index_name)):
            self._client.indices.delete(index=self.settings.index_name)
        self._client.indices.create(
            index=self.settings.index_name,
            body=build_hybrid_index(self.settings, self.embeddings),
        )
        self.ensure_pipeline()

    def ensure_pipeline(self) -> None:
        """Create or update the idempotent OpenSearch RRF search pipeline."""

        self._client.transport.perform_request(
            "PUT",
            f"/_search/pipeline/{self.settings.search_pipeline}",
            body=build_rrf_pipeline(self.settings),
        )

    def delete_index(self) -> None:
        """Delete only the derived Week 4 chunk index when it exists."""

        if bool(self._client.indices.exists(index=self.settings.index_name)):
            self._client.indices.delete(index=self.settings.index_name)

    def delete_pipeline(self) -> None:
        """Delete the derived Week 4 RRF pipeline when it exists."""

        try:
            self._client.transport.perform_request(
                "DELETE",
                f"/_search/pipeline/{self.settings.search_pipeline}",
            )
        except Exception as exc:
            if "404" not in str(exc) and "resource_not_found_exception" not in str(exc):
                raise

    def index_schema_version(self) -> int | None:
        """Read the Paperforge schema version from mapping metadata."""

        response = cast(
            dict[str, Any],
            self._client.indices.get_mapping(index=self.settings.index_name),
        )
        index_mapping = cast(dict[str, Any], response.get(self.settings.index_name, {}))
        mappings = cast(dict[str, Any], index_mapping.get("mappings", {}))
        metadata = cast(dict[str, Any], mappings.get("_meta", {}))
        value = metadata.get("paperforge_schema_version")
        return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None

    def _validate_schema(self) -> None:
        actual = self.index_schema_version()
        if actual != self.settings.schema_version:
            raise SearchIndexSchemaError(
                f"index {self.settings.index_name!r} has schema version {actual!r}; "
                f"expected {self.settings.schema_version}. Run the explicit hybrid-index rebuild."
            )

    def delete_stale_paper_chunks(self, arxiv_id: str, *, keep_chunk_ids: list[str]) -> int:
        """Delete old chunks only after their replacement batch indexed successfully."""

        if not bool(self._client.indices.exists(index=self.settings.index_name)):
            return 0
        query: dict[str, Any] = {"bool": {"filter": [{"term": {"arxiv_id": arxiv_id}}]}}
        if keep_chunk_ids:
            query["bool"]["must_not"] = [{"terms": {"chunk_id": keep_chunk_ids}}]
        response = cast(
            dict[str, Any],
            self._client.delete_by_query(
                index=self.settings.index_name,
                body={"query": query},
                conflicts="proceed",
                refresh=False,
            ),
        )
        return int(response.get("deleted", 0))

    def bulk_index(
        self,
        documents: list[HybridChunkDocument],
        *,
        refresh: bool = False,
    ) -> HybridBulkIndexResult:
        """Upsert chunk documents using deterministic chunk IDs."""

        if not documents:
            return HybridBulkIndexResult(attempted=0, indexed=0, failed=0)
        operations: list[dict[str, Any]] = []
        for document in documents:
            operations.append(
                {
                    "index": {
                        "_index": self.settings.index_name,
                        "_id": document.chunk_id,
                    }
                }
            )
            payload = document.model_dump(mode="json", exclude_none=True)
            operations.append(payload)
        response = cast(
            dict[str, Any],
            self._client.bulk(
                body=operations,
                refresh="wait_for" if refresh else False,
            ),
        )
        indexed = 0
        errors: list[str] = []
        for item in cast(list[dict[str, Any]], response.get("items", [])):
            result = cast(dict[str, Any], item.get("index", {}))
            status = int(result.get("status", 500))
            if 200 <= status < 300 and "error" not in result:
                indexed += 1
            else:
                errors.append(str(result.get("error", f"bulk item failed with status {status}")))
        return HybridBulkIndexResult(
            attempted=len(documents),
            indexed=indexed,
            failed=len(documents) - indexed,
            errors=errors,
        )

    def search(
        self,
        request: HybridSearchRequest,
        *,
        mode: ResolvedSearchMode,
        query_vector: list[float] | None,
    ) -> HybridSearchResponse:
        """Execute BM25, vector, or RRF hybrid search and normalize hits."""

        kwargs: dict[str, Any] = {
            "index": self.settings.index_name,
            "body": build_hybrid_search_query(
                request,
                mode,
                self.settings,
                query_vector,
            ),
        }
        if mode == "hybrid":
            kwargs["params"] = {"search_pipeline": self.settings.search_pipeline}
        response = cast(dict[str, Any], self._client.search(**kwargs))
        hits_block = cast(dict[str, Any], response.get("hits", {}))
        total_value = hits_block.get("total", 0)
        total = (
            int(cast(dict[str, Any], total_value).get("value", 0))
            if isinstance(total_value, dict)
            else int(total_value)
        )
        hits: list[HybridSearchHit] = []
        for raw_hit in cast(list[dict[str, Any]], hits_block.get("hits", [])):
            source = cast(dict[str, Any], raw_hit.get("_source", {}))
            highlights = cast(dict[str, list[str]], raw_hit.get("highlight", {}))
            score = raw_hit.get("_score")
            hits.append(
                HybridSearchHit(
                    **source,
                    score=float(score) if score is not None else None,
                    highlights=highlights,
                )
            )
        return HybridSearchResponse(
            query=request.query,
            requested_mode=request.mode,
            search_mode=mode,
            embeddings_used=query_vector is not None,
            total=total,
            page=request.page,
            page_size=request.page_size,
            took_ms=int(response.get("took", 0)),
            hits=hits,
        )

    def stats(self) -> HybridIndexStats:
        """Return chunk, embedding, unique-paper, and storage counts."""

        if not bool(self._client.indices.exists(index=self.settings.index_name)):
            return HybridIndexStats(
                index_name=self.settings.index_name,
                search_pipeline=self.settings.search_pipeline,
                exists=False,
            )
        response = cast(dict[str, Any], self._client.indices.stats(index=self.settings.index_name))
        index = cast(dict[str, Any], response.get("indices", {})).get(self.settings.index_name, {})
        total = cast(dict[str, Any], cast(dict[str, Any], index).get("total", {}))
        docs = cast(dict[str, Any], total.get("docs", {}))
        store = cast(dict[str, Any], total.get("store", {}))
        embedded = cast(
            dict[str, Any],
            self._client.count(
                index=self.settings.index_name,
                body={"query": {"term": {"has_embedding": True}}},
            ),
        )
        unique = cast(
            dict[str, Any],
            self._client.search(
                index=self.settings.index_name,
                body={
                    "size": 0,
                    "aggs": {"papers": {"cardinality": {"field": "arxiv_id"}}},
                },
            ),
        )
        aggregations = cast(dict[str, Any], unique.get("aggregations", {}))
        papers = cast(dict[str, Any], aggregations.get("papers", {}))
        return HybridIndexStats(
            index_name=self.settings.index_name,
            search_pipeline=self.settings.search_pipeline,
            exists=True,
            schema_version=self.index_schema_version(),
            document_count=int(docs.get("count", 0)),
            embedded_document_count=int(embedded.get("count", 0)),
            unique_paper_count=int(papers.get("value", 0)),
            deleted_count=int(docs.get("deleted", 0)),
            size_in_bytes=int(store.get("size_in_bytes", 0)),
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._client.close()
