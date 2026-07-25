"""Tests for PostgreSQL-to-OpenSearch projection."""

from datetime import UTC, datetime
from typing import cast
from unittest.mock import MagicMock
from uuid import uuid4

from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.search import BulkIndexResult
from paperforge.services.search_indexing import SearchIndexingService


def _paper() -> Paper:
    now = datetime.now(UTC)
    paper = Paper(
        id=uuid4(),
        arxiv_id="2607.00001",
        title="AI Agents",
        authors=["Ada Lovelace"],
        abstract="Agent systems",
        categories=["cs.AI"],
        published_date=now,
        pdf_url="https://arxiv.org/pdf/2607.00001",
        raw_text="full text",
        pdf_processed=True,
    )
    paper.created_at = now
    paper.updated_at = now
    return paper


def test_indexing_service_projects_and_batches_papers() -> None:
    repository = MagicMock()
    repository.iter_for_search_index.return_value = [[_paper()]]
    client = MagicMock()
    client.settings.index_name = "paperforge-papers-bm25-v1"
    client.bulk_index.return_value = BulkIndexResult(attempted=1, indexed=1, failed=0)
    service = SearchIndexingService(
        cast(PaperRepository, repository),
        cast(OpenSearchClient, client),
    )

    report = service.run(batch_size=100, refresh=True)

    assert report.indexed == 1
    assert report.batches == 1
    client.ensure_index.assert_called_once_with()
    document = client.bulk_index.call_args.args[0][0]
    assert document.arxiv_id == "2607.00001"
    assert document.raw_text == "full text"


def test_rebuild_recreates_only_search_index() -> None:
    repository = MagicMock()
    repository.iter_for_search_index.return_value = []
    client = MagicMock()
    client.settings.index_name = "paperforge-papers-bm25-v1"
    service = SearchIndexingService(
        cast(PaperRepository, repository),
        cast(OpenSearchClient, client),
    )

    report = service.run(batch_size=10, rebuild=True)

    assert report.rebuilt is True
    client.recreate_index.assert_called_once_with()
    client.ensure_index.assert_not_called()
