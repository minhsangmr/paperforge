"""Tests for per-paper graceful degradation in the ingestion orchestrator."""

from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from paperforge.core.config import IngestionSettings
from paperforge.schemas.papers import ArxivPaper, DocumentSection, ParsedDocument
from paperforge.services.arxiv.client import PdfDownload
from paperforge.services.ingestion import IngestionService


class _FakeArxiv:
    def __init__(self, papers: list[ArxivPaper]) -> None:
        self.papers = papers

    async def fetch_papers(self, **_: object) -> list[ArxivPaper]:
        return self.papers

    async def download_pdf(self, paper: ArxivPaper, *, force: bool = False) -> PdfDownload:
        del force
        return PdfDownload(path=Path(f"/tmp/{paper.arxiv_id}.pdf"), cache_hit=True)


class _MetadataOnlyArxiv(_FakeArxiv):
    def __init__(self, papers: list[ArxivPaper]) -> None:
        super().__init__(papers)
        self.download_called = False

    async def download_pdf(
        self,
        paper: ArxivPaper,
        *,
        force: bool = False,
    ) -> PdfDownload:
        del paper, force
        self.download_called = True
        raise AssertionError("metadata-only ingestion must not download PDFs")


class _FakeParser:
    async def parse(self, path: Path) -> ParsedDocument:
        if "bad" in path.name:
            raise RuntimeError("cannot parse")
        return ParsedDocument(
            raw_text="Full text",
            sections=[DocumentSection(title="Content", content="Full text")],
            parser_used="docling",
        )


def _paper(arxiv_id: str) -> ArxivPaper:
    return ArxivPaper(
        arxiv_id=arxiv_id,
        title="Title",
        authors=["Alice"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 20, tzinfo=UTC),
        pdf_url=f"https://arxiv.org/pdf/{arxiv_id}",
    )


@pytest.mark.asyncio
async def test_pipeline_stores_metadata_when_one_pdf_parse_fails() -> None:
    arxiv = _FakeArxiv([_paper("good"), _paper("bad")])
    service = IngestionService(
        arxiv,
        _FakeParser(),
        IngestionSettings(max_concurrent_downloads=2, max_concurrent_parses=1),
        "cs.AI",
    )
    session = MagicMock()
    session.begin_nested.side_effect = lambda: nullcontext()
    repository = MagicMock()
    repository.upsert.side_effect = [
        MagicMock(created=True),
        MagicMock(created=False),
    ]

    with patch("paperforge.services.ingestion.PaperRepository", return_value=repository):
        report = await service.run(session)

    assert report.papers_fetched == 2
    assert report.pdfs_available == 2
    assert report.pdf_cache_hits == 2
    assert report.pdfs_parsed == 1
    assert report.papers_created == 1
    assert report.papers_updated == 1
    assert len(report.issues) == 1
    assert report.issues[0].stage == "parse"
    assert repository.upsert.call_count == 2


@pytest.mark.asyncio
async def test_metadata_only_pipeline_does_not_download() -> None:
    arxiv = _MetadataOnlyArxiv([_paper("metadata-only")])
    service = IngestionService(
        arxiv,
        _FakeParser(),
        IngestionSettings(),
        "cs.AI",
    )
    session = MagicMock()
    session.begin_nested.side_effect = lambda: nullcontext()
    repository = MagicMock()
    repository.upsert.return_value = MagicMock(created=True)

    with patch("paperforge.services.ingestion.PaperRepository", return_value=repository):
        report = await service.run(session, process_pdfs=False)

    assert report.pdfs_available == 0
    assert report.pdfs_parsed == 0
    assert arxiv.download_called is False


class _FailingArxiv(_FakeArxiv):
    async def fetch_papers(self, **_: object) -> list[ArxivPaper]:
        from paperforge.exceptions import ArxivResponseError

        raise ArxivResponseError("source unavailable")


@pytest.mark.asyncio
async def test_pipeline_wraps_metadata_source_failure() -> None:
    from paperforge.exceptions import IngestionPipelineError

    service = IngestionService(
        _FailingArxiv([]),
        _FakeParser(),
        IngestionSettings(),
        "cs.AI",
    )

    with pytest.raises(IngestionPipelineError, match="metadata fetch failed"):
        await service.run(MagicMock())


@pytest.mark.asyncio
async def test_pipeline_records_database_failure_and_continues() -> None:
    arxiv = _FakeArxiv([_paper("first"), _paper("second")])
    service = IngestionService(
        arxiv,
        _FakeParser(),
        IngestionSettings(max_concurrent_downloads=2),
        "cs.AI",
    )
    session = MagicMock()
    session.begin_nested.side_effect = lambda: nullcontext()
    repository = MagicMock()
    repository.upsert.side_effect = [RuntimeError("database write failed"), MagicMock(created=True)]

    with patch("paperforge.services.ingestion.PaperRepository", return_value=repository):
        report = await service.run(session)

    assert report.papers_created == 1
    assert report.papers_updated == 0
    assert any(issue.stage == "database" for issue in report.issues)


@pytest.mark.asyncio
async def test_successful_parse_is_mapped_to_persistence_payload() -> None:
    service = IngestionService(
        _FakeArxiv([_paper("mapped")]),
        _FakeParser(),
        IngestionSettings(),
        "cs.AI",
    )
    session = MagicMock()
    session.begin_nested.side_effect = lambda: nullcontext()
    repository = MagicMock()
    repository.upsert.return_value = MagicMock(created=True)

    with patch("paperforge.services.ingestion.PaperRepository", return_value=repository):
        report = await service.run(session)

    payload = repository.upsert.call_args.args[0]
    assert report.pdfs_parsed == 1
    assert payload.pdf_processed is True
    assert payload.raw_text == "Full text"
    assert payload.parser_used == "docling"
