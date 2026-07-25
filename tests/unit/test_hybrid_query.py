"""Unit tests for BM25, k-NN, and hybrid OpenSearch query bodies."""

from typing import Any, cast

import pytest

from paperforge.core.config import HybridSearchSettings
from paperforge.schemas.hybrid_search import HybridSearchRequest
from paperforge.services.hybrid_query import build_hybrid_search_query


def test_builds_bm25_vector_and_hybrid_queries() -> None:
    settings = HybridSearchSettings(max_candidate_count=100, candidate_multiplier=4)
    request = HybridSearchRequest(
        query="semantic retrieval",
        categories=["cs.AI"],
        page=2,
        page_size=5,
    )
    bm25 = build_hybrid_search_query(request, "bm25", settings, None)
    vector = build_hybrid_search_query(request, "vector", settings, [0.1] * 4)
    hybrid = build_hybrid_search_query(request, "hybrid", settings, [0.1] * 4)
    assert bm25["from"] == 5
    assert "bool" in cast(dict[str, Any], bm25["query"])
    vector_query = cast(dict[str, Any], vector["query"])
    knn_fields = cast(dict[str, Any], vector_query["knn"])
    knn = cast(dict[str, Any], knn_fields[settings.embedding_field])
    assert knn["k"] == 20
    filter_body = cast(dict[str, Any], knn["filter"])
    bool_filter = cast(dict[str, Any], filter_body["bool"])
    assert cast(list[dict[str, Any]], bool_filter["filter"])[0] == {
        "terms": {"categories": ["cs.AI"]}
    }
    hybrid_query = cast(dict[str, Any], hybrid["query"])
    assert len(cast(dict[str, list[dict[str, Any]]], hybrid_query["hybrid"])["queries"]) == 2


def test_vector_modes_require_embedding() -> None:
    request = HybridSearchRequest(query="x")
    with pytest.raises(ValueError, match="requires"):
        build_hybrid_search_query(request, "hybrid", HybridSearchSettings(), None)
