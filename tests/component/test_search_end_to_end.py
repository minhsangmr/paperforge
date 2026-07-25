"""End-to-end PostgreSQL to OpenSearch BM25 component test."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import delete

from paperforge.core.config import get_settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.search import SearchRequest
from paperforge.services.search_indexing import SearchIndexingService

pytestmark = pytest.mark.component


def test_postgres_to_bm25_search_round_trip() -> None:
    settings = get_settings()
    suffix = uuid4().hex[:10]
    search_settings = settings.opensearch.model_copy(
        update={"index_name": f"paperforge-component-{suffix}"}
    )
    arxiv_id = f"component.{suffix}"
    database = Database(settings.database)
    client = OpenSearchClient(search_settings)
    try:
        with database.session() as session:
            session.add(
                Paper(
                    arxiv_id=arxiv_id,
                    title="Agentic Retrieval for Scientific Search",
                    authors=["Paperforge Test"],
                    abstract="A deterministic BM25 retrieval component test.",
                    categories=["cs.AI"],
                    published_date=datetime.now(UTC),
                    pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
                    raw_text="agentic retrieval with interpretable keyword ranking",
                    pdf_processed=True,
                )
            )

        with database.session() as session:
            report = SearchIndexingService(PaperRepository(session), client).run(
                batch_size=25,
                refresh=True,
            )
        assert report.failed == 0

        response = client.search(
            SearchRequest(
                query="agentic retrieval",
                categories=["cs.AI"],
                page_size=10,
            )
        )
        assert any(hit.arxiv_id == arxiv_id for hit in response.hits)
    finally:
        client.delete_index()
        client.close()
        with database.session() as session:
            session.execute(delete(Paper).where(Paper.arxiv_id == arxiv_id))
        database.close()
