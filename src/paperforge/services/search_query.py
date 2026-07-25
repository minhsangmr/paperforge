"""Pure OpenSearch BM25 query construction."""

from datetime import timedelta
from typing import Any

from paperforge.core.config import OpenSearchSettings
from paperforge.schemas.search import SearchRequest


def _date_range(request: SearchRequest) -> dict[str, Any] | None:
    bounds: dict[str, str] = {}
    if request.published_from is not None:
        bounds["gte"] = request.published_from.isoformat()
    if request.published_to is not None:
        exclusive_end = request.published_to + timedelta(days=1)
        bounds["lt"] = exclusive_end.isoformat()
    return {"range": {"published_date": bounds}} if bounds else None


def build_bm25_query(
    request: SearchRequest,
    settings: OpenSearchSettings,
) -> dict[str, Any]:
    """Build a safe, explainable BM25 query for academic-paper search."""

    filters: list[dict[str, Any]] = []
    if request.categories:
        filters.append({"terms": {"categories": request.categories}})
    date_filter = _date_range(request)
    if date_filter is not None:
        filters.append(date_filter)
    if request.processed_only:
        filters.append({"term": {"pdf_processed": True}})

    normalized = request.query.strip()
    if normalized == "*":
        base_query: dict[str, Any] = {"match_all": {}}
    else:
        should: list[dict[str, Any]] = [
            {"term": {"arxiv_id": {"value": normalized, "boost": 12.0}}},
            {"match_phrase": {"title": {"query": normalized, "boost": 6.0}}},
            {
                "multi_match": {
                    "query": normalized,
                    "fields": ["title^4", "abstract^2", "raw_text", "authors^1.5"],
                    "type": "best_fields",
                    "tie_breaker": 0.3,
                    "minimum_should_match": "75%",
                }
            },
        ]
        if len(normalized) >= settings.fuzzy_min_length:
            should.append(
                {
                    "multi_match": {
                        "query": normalized,
                        "fields": ["title^2", "abstract"],
                        "type": "best_fields",
                        "fuzziness": "AUTO:4,7",
                        "prefix_length": 1,
                        "max_expansions": 25,
                        "boost": 0.35,
                    }
                }
            )
        base_query = {"bool": {"should": should, "minimum_should_match": 1}}

    if filters:
        query: dict[str, Any] = {"bool": {"must": [base_query], "filter": filters}}
    else:
        query = base_query

    if request.sort == "published_desc":
        sort: list[Any] = [{"published_date": {"order": "desc"}}, "_score"]
    elif request.sort == "published_asc":
        sort = [{"published_date": {"order": "asc"}}, "_score"]
    else:
        sort = ["_score", {"published_date": {"order": "desc"}}]

    return {
        "from": request.offset,
        "size": request.page_size,
        "track_total_hits": True,
        "query": query,
        "sort": sort,
        "_source": {
            "includes": [
                "arxiv_id",
                "title",
                "authors",
                "abstract",
                "categories",
                "published_date",
                "pdf_url",
                "pdf_processed",
            ]
        },
        "highlight": {
            "pre_tags": ["<mark>"],
            "post_tags": ["</mark>"],
            "require_field_match": False,
            "fields": {
                "title": {"number_of_fragments": 0},
                "abstract": {
                    "fragment_size": settings.highlight_fragment_size,
                    "number_of_fragments": 2,
                },
                "raw_text": {
                    "fragment_size": settings.highlight_fragment_size,
                    "number_of_fragments": 2,
                },
            },
        },
    }
