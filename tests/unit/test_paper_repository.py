"""Tests for transaction-neutral paper repository behavior."""

from datetime import UTC, datetime
from unittest.mock import MagicMock

from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.papers import PaperUpsert


def _payload(*, processed: bool = False) -> PaperUpsert:
    return PaperUpsert(
        arxiv_id="2607.01234v1",
        title="Title",
        authors=["Alice"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 20, tzinfo=UTC),
        pdf_url="https://arxiv.org/pdf/2607.01234v1",
        raw_text="Full text" if processed else None,
        sections=[{"title": "Content", "content": "Full text", "level": 1}] if processed else None,
        parser_used="docling" if processed else None,
        parser_metadata={"source": "test"},
        pdf_processed=processed,
        pdf_processing_date=datetime(2026, 7, 21, tzinfo=UTC) if processed else None,
    )


def test_upsert_creates_without_committing() -> None:
    session = MagicMock()
    session.scalar.return_value = None
    repository = PaperRepository(session)

    outcome = repository.upsert(_payload(processed=True))

    assert outcome.created is True
    assert outcome.paper.pdf_processed is True
    session.add.assert_called_once_with(outcome.paper)
    session.flush.assert_called_once_with()
    session.commit.assert_not_called()


def test_metadata_only_update_preserves_existing_parsed_content() -> None:
    existing = Paper(
        arxiv_id="2607.01234v1",
        title="Old",
        authors=["Old"],
        abstract="Old abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 19, tzinfo=UTC),
        pdf_url="https://example.test/old.pdf",
        raw_text="Keep me",
        sections=[{"title": "Old", "content": "Keep me"}],
        references=[],
        parser_used="docling",
        parser_metadata={"successful": True},
        pdf_processed=True,
        pdf_processing_date=datetime(2026, 7, 20, tzinfo=UTC),
    )
    session = MagicMock()
    session.scalar.return_value = existing
    repository = PaperRepository(session)

    outcome = repository.upsert(_payload(processed=False))

    assert outcome.created is False
    assert existing.title == "Title"
    assert existing.raw_text == "Keep me"
    assert existing.parser_metadata == {"successful": True}
    assert existing.pdf_processed is True
    session.commit.assert_not_called()


def test_stats_aggregates_three_counts() -> None:
    session = MagicMock()
    session.scalar.side_effect = [8, 5, 4]

    stats = PaperRepository(session).stats()

    assert (stats.total, stats.processed, stats.with_text) == (8, 5, 4)


def test_successful_parse_replaces_previous_content() -> None:
    existing = Paper(
        arxiv_id="2607.01234v1",
        title="Old",
        authors=["Old"],
        abstract="Old abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 19, tzinfo=UTC),
        pdf_url="https://example.test/old.pdf",
        raw_text=None,
        sections=None,
        references=None,
        parser_used=None,
        parser_metadata=None,
        pdf_processed=False,
        pdf_processing_date=None,
    )
    session = MagicMock()
    session.scalar.return_value = existing
    repository = PaperRepository(session)

    outcome = repository.upsert(_payload(processed=True))

    assert outcome.created is False
    assert existing.raw_text == "Full text"
    assert existing.parser_used == "docling"
    assert existing.pdf_processed is True
    assert existing.pdf_processing_date is not None
