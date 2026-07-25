"""OpenSearch query builders for BM25, vector, and RRF hybrid retrieval."""

from datetime import timedelta
from typing import Any

from paperforge.core.config import HybridSearchSettings
from paperforge.schemas.hybrid_search import HybridSearchRequest, ResolvedSearchMode


def _filters(request: HybridSearchRequest) -> list[dict[str, Any]]:
    filters: list[dict[str, Any]] = []
    if request.categories:
        filters.append({"terms": {"categories": request.categories}})
    bounds: dict[str, str] = {}
    if request.published_from is not None:
        bounds["gte"] = request.published_from.isoformat()
    if request.published_to is not None:
        bounds["lt"] = (request.published_to + timedelta(days=1)).isoformat()
    if bounds:
        filters.append({"range": {"published_date": bounds}})
    return filters


def _bm25_clause(request: HybridSearchRequest) -> dict[str, Any]:
    text_query: dict[str, Any] = {
        "bool": {
            "should": [
                {"term": {"arxiv_id": {"value": request.query, "boost": 12.0}}},
                {"match_phrase": {"title": {"query": request.query, "boost": 6.0}}},
                {
                    "multi_match": {
                        "query": request.query,
                        "fields": [
                            "title^4",
                            "abstract^2",
                            "section_title^1.5",
                            "chunk_text",
                            "authors^1.5",
                        ],
                        "type": "best_fields",
                        "tie_breaker": 0.3,
                        "minimum_should_match": "70%",
                    }
                },
            ],
            "minimum_should_match": 1,
        }
    }
    filters = _filters(request)
    if not filters:
        return text_query
    return {"bool": {"must": [text_query], "filter": filters}}


def _knn_clause(
    request: HybridSearchRequest,
    vector: list[float],
    settings: HybridSearchSettings,
) -> dict[str, Any]:
    candidate_count = min(
        settings.max_candidate_count,
        max(
            request.offset + request.page_size,
            request.page_size * settings.candidate_multiplier,
        ),
    )
    vector_body: dict[str, Any] = {"vector": vector, "k": candidate_count}
    filters = _filters(request)
    if filters:
        vector_body["filter"] = {"bool": {"filter": filters}}
    return {"knn": {settings.embedding_field: vector_body}}


def build_hybrid_search_query(
    request: HybridSearchRequest,
    mode: ResolvedSearchMode,
    settings: HybridSearchSettings,
    query_vector: list[float] | None,
) -> dict[str, Any]:
    """Build a mode-specific chunk query while excluding vectors from responses."""

    if mode in {"vector", "hybrid"} and query_vector is None:
        raise ValueError(f"{mode} search requires a query embedding")
    bm25 = _bm25_clause(request)
    if mode == "bm25":
        query = bm25
    elif mode == "vector":
        query = _knn_clause(request, query_vector or [], settings)
    else:
        query = {
            "hybrid": {
                "queries": [
                    bm25,
                    _knn_clause(request, query_vector or [], settings),
                ]
            }
        }

    return {
        "from": request.offset,
        "size": request.page_size,
        "track_total_hits": True,
        "query": query,
        "_source": {"excludes": [settings.embedding_field]},
        "highlight": {
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "require_field_match": False,
            "fields": {
                "title": {"number_of_fragments": 0},
                "section_title": {"number_of_fragments": 0},
                "chunk_text": {
                    "fragment_size": settings.highlight_fragment_size,
                    "number_of_fragments": 2,
                },
            },
        },
    }
