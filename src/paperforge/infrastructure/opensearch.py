"""OpenSearch connectivity, versioned BM25 index management, and document I/O."""

from typing import Any, cast
from urllib.parse import urlparse

from opensearchpy import OpenSearch

from paperforge.core.config import OpenSearchSettings
from paperforge.exceptions import SearchIndexSchemaError
from paperforge.schemas.search import (
    BulkIndexResult,
    PaperSearchDocument,
    SearchHit,
    SearchIndexStats,
    SearchRequest,
    SearchResponse,
)
from paperforge.services.search_query import build_bm25_query


def build_paper_index(settings: OpenSearchSettings) -> dict[str, Any]:
    """Return the immutable Week 3 index definition."""

    return {
        "settings": {
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
            "similarity": {
                "paperforge_bm25": {
                    "type": "BM25",
                    "k1": 1.2,
                    "b": 0.75,
                }
            },
        },
        "mappings": {
            "dynamic": "strict",
            "_meta": {
                "paperforge_schema_version": settings.schema_version,
                "purpose": "week3-paper-level-bm25",
            },
            "properties": {
                "id": {"type": "keyword"},
                "arxiv_id": {
                    "type": "keyword",
                    "normalizer": "paperforge_lowercase",
                },
                "title": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                    "fields": {
                        "raw": {
                            "type": "keyword",
                            "normalizer": "paperforge_lowercase",
                            "ignore_above": 512,
                        }
                    },
                },
                "authors": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                    "fields": {
                        "raw": {
                            "type": "keyword",
                            "normalizer": "paperforge_lowercase",
                            "ignore_above": 256,
                        }
                    },
                },
                "abstract": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                },
                "categories": {"type": "keyword"},
                "published_date": {"type": "date"},
                "pdf_url": {"type": "keyword", "index": False},
                "raw_text": {
                    "type": "text",
                    "analyzer": "paperforge_english",
                    "similarity": "paperforge_bm25",
                },
                "pdf_processed": {"type": "boolean"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
            },
        },
    }


BASE_PAPER_INDEX: dict[str, Any] = build_paper_index(OpenSearchSettings())


class OpenSearchClient:
    """Typed adapter around opensearch-py for Week 3 paper search."""

    def __init__(self, settings: OpenSearchSettings, client: Any | None = None) -> None:
        self.settings = settings
        self._client: Any = client or self._build_client(settings)

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

    def ping(self) -> bool:
        """Return true when the cluster is reachable and not red."""

        health = cast(dict[str, Any], self._client.cluster.health())
        return health.get("status") in {"green", "yellow"}

    def ensure_index(self) -> bool:
        """Create the BM25 index once and reject incompatible existing mappings."""

        if bool(self._client.indices.exists(index=self.settings.index_name)):
            actual_version = self.index_schema_version()
            if actual_version != self.settings.schema_version:
                raise SearchIndexSchemaError(
                    f"index {self.settings.index_name!r} has schema version "
                    f"{actual_version!r}; expected {self.settings.schema_version}. "
                    "Use a new index name or run the explicit search-index rebuild command."
                )
            return False
        try:
            self._client.indices.create(
                index=self.settings.index_name,
                body=build_paper_index(self.settings),
            )
        except Exception as exc:
            if "resource_already_exists_exception" not in str(exc):
                raise
            actual_version = self.index_schema_version()
            if actual_version != self.settings.schema_version:
                raise SearchIndexSchemaError(
                    f"index {self.settings.index_name!r} was concurrently created "
                    "with an incompatible schema"
                ) from exc
            return False
        return True

    def recreate_index(self) -> None:
        """Delete and recreate only the derived search index."""

        if bool(self._client.indices.exists(index=self.settings.index_name)):
            self._client.indices.delete(index=self.settings.index_name)
        self._client.indices.create(
            index=self.settings.index_name,
            body=build_paper_index(self.settings),
        )

    def delete_index(self) -> bool:
        """Delete only the configured derived search index when it exists."""

        if not bool(self._client.indices.exists(index=self.settings.index_name)):
            return False
        self._client.indices.delete(index=self.settings.index_name)
        return True

    def index_schema_version(self) -> int | None:
        """Read the Paperforge schema version from index mapping metadata."""

        response = cast(
            dict[str, Any],
            self._client.indices.get_mapping(index=self.settings.index_name),
        )
        index_mapping = cast(dict[str, Any], response.get(self.settings.index_name, {}))
        mappings = cast(dict[str, Any], index_mapping.get("mappings", {}))
        metadata = cast(dict[str, Any], mappings.get("_meta", {}))
        value = metadata.get("paperforge_schema_version")
        return int(value) if isinstance(value, (int, str)) and str(value).isdigit() else None

    def bulk_index(
        self,
        documents: list[PaperSearchDocument],
        *,
        refresh: bool = False,
    ) -> BulkIndexResult:
        """Upsert a batch using stable arXiv IDs as OpenSearch document IDs."""

        if not documents:
            return BulkIndexResult(attempted=0, indexed=0, failed=0)

        operations: list[dict[str, Any]] = []
        for document in documents:
            operations.append(
                {
                    "index": {
                        "_index": self.settings.index_name,
                        "_id": document.arxiv_id,
                    }
                }
            )
            operations.append(document.model_dump(mode="json"))

        response = cast(
            dict[str, Any],
            self._client.bulk(
                body=operations,
                refresh="wait_for" if refresh else False,
            ),
        )
        errors: list[str] = []
        indexed = 0
        for item in cast(list[dict[str, Any]], response.get("items", [])):
            result = cast(dict[str, Any], item.get("index", {}))
            status = int(result.get("status", 500))
            if 200 <= status < 300 and "error" not in result:
                indexed += 1
            else:
                errors.append(str(result.get("error", f"bulk item failed with status {status}")))
        failed = len(documents) - indexed
        return BulkIndexResult(
            attempted=len(documents),
            indexed=indexed,
            failed=failed,
            errors=errors,
        )

    def search(self, request: SearchRequest) -> SearchResponse:
        """Execute a validated BM25 request and normalize the response."""

        response = cast(
            dict[str, Any],
            self._client.search(
                index=self.settings.index_name,
                body=build_bm25_query(request, self.settings),
            ),
        )
        hits_block = cast(dict[str, Any], response.get("hits", {}))
        total_value = hits_block.get("total", 0)
        total = (
            int(cast(dict[str, Any], total_value).get("value", 0))
            if isinstance(total_value, dict)
            else int(total_value)
        )
        hits: list[SearchHit] = []
        for raw_hit in cast(list[dict[str, Any]], hits_block.get("hits", [])):
            source = cast(dict[str, Any], raw_hit.get("_source", {}))
            highlight = cast(dict[str, list[str]], raw_hit.get("highlight", {}))
            score_value = raw_hit.get("_score")
            hits.append(
                SearchHit(
                    **source,
                    score=float(score_value) if score_value is not None else None,
                    highlights=highlight,
                )
            )
        return SearchResponse(
            query=request.query,
            total=total,
            page=request.page,
            page_size=request.page_size,
            took_ms=int(response.get("took", 0)),
            hits=hits,
        )

    def stats(self) -> SearchIndexStats:
        """Return document count and storage information for the configured index."""

        if not bool(self._client.indices.exists(index=self.settings.index_name)):
            return SearchIndexStats(index_name=self.settings.index_name, exists=False)
        response = cast(
            dict[str, Any],
            self._client.indices.stats(index=self.settings.index_name),
        )
        index = cast(dict[str, Any], response.get("indices", {})).get(self.settings.index_name, {})
        total = cast(dict[str, Any], cast(dict[str, Any], index).get("total", {}))
        docs = cast(dict[str, Any], total.get("docs", {}))
        store = cast(dict[str, Any], total.get("store", {}))
        return SearchIndexStats(
            index_name=self.settings.index_name,
            exists=True,
            schema_version=self.index_schema_version(),
            document_count=int(docs.get("count", 0)),
            deleted_count=int(docs.get("deleted", 0)),
            size_in_bytes=int(store.get("size_in_bytes", 0)),
        )

    def close(self) -> None:
        """Close the underlying HTTP connection pool."""

        self._client.close()
