"""Tests for pure BM25 query construction."""

from datetime import date

from paperforge.core.config import OpenSearchSettings
from paperforge.schemas.search import SearchRequest
from paperforge.services.search_query import build_bm25_query


def test_two_letter_query_avoids_fuzzy_expansion() -> None:
    body = build_bm25_query(SearchRequest(query="AI"), OpenSearchSettings())

    should = body["query"]["bool"]["should"]
    assert len(should) == 3
    assert should[0]["term"]["arxiv_id"]["boost"] == 12.0
    assert body["sort"][0] == "_score"


def test_long_query_adds_low_weight_fuzzy_fallback() -> None:
    body = build_bm25_query(
        SearchRequest(query="transformr architecture"),
        OpenSearchSettings(),
    )

    should = body["query"]["bool"]["should"]
    assert len(should) == 4
    assert should[-1]["multi_match"]["fuzziness"] == "AUTO:4,7"


def test_filters_dates_pagination_and_sort() -> None:
    request = SearchRequest(
        query="agents",
        categories=["cs.AI", "cs.LG"],
        published_from=date(2026, 7, 1),
        published_to=date(2026, 7, 24),
        processed_only=True,
        page=3,
        page_size=20,
        sort="published_desc",
    )

    body = build_bm25_query(request, OpenSearchSettings())

    assert body["from"] == 40
    assert body["size"] == 20
    filters = body["query"]["bool"]["filter"]
    assert {"terms": {"categories": ["cs.AI", "cs.LG"]}} in filters
    assert {"term": {"pdf_processed": True}} in filters
    assert {"range": {"published_date": {"gte": "2026-07-01", "lt": "2026-07-25"}}} in filters
    assert body["sort"][0] == {"published_date": {"order": "desc"}}


def test_wildcard_query_uses_match_all() -> None:
    body = build_bm25_query(SearchRequest(query="*"), OpenSearchSettings())

    assert body["query"] == {"match_all": {}}
