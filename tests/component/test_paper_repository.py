"""Paper upsert component test against PostgreSQL."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import delete

from paperforge.core.config import get_settings
from paperforge.infrastructure.database import Database
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.papers import PaperUpsert

pytestmark = pytest.mark.component


def test_repository_upsert_is_idempotent_and_preserves_parsed_content() -> None:
    database = Database(get_settings().database)
    arxiv_id = "component.2607.00001v1"
    try:
        with database.session() as session:
            session.execute(delete(Paper).where(Paper.arxiv_id == arxiv_id))
            repository = PaperRepository(session)
            created = repository.upsert(
                PaperUpsert(
                    arxiv_id=arxiv_id,
                    title="Initial",
                    authors=["Alice"],
                    abstract="Abstract",
                    categories=["cs.AI"],
                    published_date=datetime(2026, 7, 20, tzinfo=UTC),
                    pdf_url="https://arxiv.org/pdf/component.2607.00001v1",
                    raw_text="Parsed content",
                    sections=[{"title": "Content", "content": "Parsed content", "level": 1}],
                    parser_used="docling",
                    parser_metadata={"test": True},
                    pdf_processed=True,
                    pdf_processing_date=datetime(2026, 7, 21, tzinfo=UTC),
                )
            )
            assert created.created is True

        with database.session() as session:
            repository = PaperRepository(session)
            updated = repository.upsert(
                PaperUpsert(
                    arxiv_id=arxiv_id,
                    title="Updated",
                    authors=["Alice"],
                    abstract="Updated abstract",
                    categories=["cs.AI"],
                    published_date=datetime(2026, 7, 20, tzinfo=UTC),
                    pdf_url="https://arxiv.org/pdf/component.2607.00001v1",
                )
            )
            assert updated.created is False
            assert updated.paper.title == "Updated"
            assert updated.paper.raw_text == "Parsed content"
            assert updated.paper.pdf_processed is True
    finally:
        with database.session() as session:
            session.execute(delete(Paper).where(Paper.arxiv_id == arxiv_id))
        database.close()
