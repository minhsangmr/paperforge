"""Tests for versioned OpenSearch index and result normalization."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from paperforge.core.config import OpenSearchSettings
from paperforge.exceptions import SearchIndexSchemaError
from paperforge.infrastructure.opensearch import OpenSearchClient, build_paper_index
from paperforge.schemas.search import PaperSearchDocument, SearchRequest


def _mapping(version: int | None) -> dict[str, object]:
    metadata = {} if version is None else {"paperforge_schema_version": version}
    return {"paperforge-papers-bm25-v1": {"mappings": {"_meta": metadata}}}


def test_opensearch_bootstrap_is_idempotent() -> None:
    raw_client = MagicMock()
    raw_client.indices.exists.side_effect = [False, True]
    raw_client.indices.get_mapping.return_value = _mapping(1)
    raw_client.cluster.health.return_value = {"status": "yellow"}
    settings = OpenSearchSettings()
    adapter = OpenSearchClient(settings, client=raw_client)

    assert adapter.ping() is True
    assert adapter.ensure_index() is True
    assert adapter.ensure_index() is False
    adapter.close()

    raw_client.indices.create.assert_called_once_with(
        index=settings.index_name,
        body=build_paper_index(settings),
    )
    raw_client.close.assert_called_once_with()


def test_existing_unversioned_index_is_rejected() -> None:
    raw_client = MagicMock()
    raw_client.indices.exists.return_value = True
    raw_client.indices.get_mapping.return_value = _mapping(None)
    adapter = OpenSearchClient(OpenSearchSettings(), client=raw_client)

    with pytest.raises(SearchIndexSchemaError, match="schema version"):
        adapter.ensure_index()


def test_bulk_index_uses_stable_arxiv_id() -> None:
    raw_client = MagicMock()
    raw_client.bulk.return_value = {"items": [{"index": {"status": 201}}]}
    adapter = OpenSearchClient(OpenSearchSettings(), client=raw_client)
    now = datetime.now(UTC)
    document = PaperSearchDocument(
        id="database-id",
        arxiv_id="2607.00001",
        title="AI Agents",
        authors=["Ada Lovelace"],
        abstract="Agent systems",
        categories=["cs.AI"],
        published_date=now,
        pdf_url="https://arxiv.org/pdf/2607.00001",
        raw_text="full text",
        pdf_processed=True,
        created_at=now,
        updated_at=now,
    )

    result = adapter.bulk_index([document], refresh=True)

    assert result.indexed == 1
    operations = raw_client.bulk.call_args.kwargs["body"]
    assert operations[0]["index"]["_id"] == "2607.00001"
    assert raw_client.bulk.call_args.kwargs["refresh"] == "wait_for"


def test_search_response_is_normalized() -> None:
    raw_client = MagicMock()
    raw_client.search.return_value = {
        "took": 7,
        "hits": {
            "total": {"value": 1, "relation": "eq"},
            "hits": [
                {
                    "_score": 4.2,
                    "_source": {
                        "arxiv_id": "2607.00001",
                        "title": "AI Agents",
                        "authors": ["Ada Lovelace"],
                        "abstract": "Agent systems",
                        "categories": ["cs.AI"],
                        "published_date": "2026-07-24T00:00:00Z",
                        "pdf_url": "https://arxiv.org/pdf/2607.00001",
                        "pdf_processed": True,
                    },
                    "highlight": {"title": ["<mark>AI</mark> Agents"]},
                }
            ],
        },
    }
    adapter = OpenSearchClient(OpenSearchSettings(), client=raw_client)

    response = adapter.search(SearchRequest(query="AI"))

    assert response.total == 1
    assert response.took_ms == 7
    assert response.hits[0].score == 4.2
    assert response.hits[0].highlights["title"] == ["<mark>AI</mark> Agents"]


def test_opensearch_client_parses_url() -> None:
    with patch("paperforge.infrastructure.opensearch.OpenSearch") as constructor:
        OpenSearchClient(OpenSearchSettings(url="https://user:secret@search.example:9443"))

    kwargs = constructor.call_args.kwargs
    assert kwargs["hosts"] == [{"host": "search.example", "port": 9443, "scheme": "https"}]
    assert kwargs["http_auth"] == ("user", "secret")
    assert kwargs["verify_certs"] is True
