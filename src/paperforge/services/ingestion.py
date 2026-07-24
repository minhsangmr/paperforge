"""End-to-end arXiv metadata, PDF parsing, and PostgreSQL ingestion."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy.orm import Session

from paperforge.core.config import IngestionSettings
from paperforge.exceptions import IngestionPipelineError, PaperforgeError
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.papers import (
    ArxivPaper,
    IngestionIssue,
    IngestionReport,
    PaperUpsert,
    ParsedDocument,
)
from paperforge.services.arxiv.client import PdfDownload

logger = logging.getLogger(__name__)


class ArxivSource(Protocol):
    """Minimum arXiv operations required by the ingestion orchestrator."""

    async def fetch_papers(
        self,
        *,
        max_results: int | None = None,
        start: int = 0,
        from_date: str | None = None,
        to_date: str | None = None,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> list[ArxivPaper]: ...

    async def download_pdf(
        self,
        paper: ArxivPaper,
        *,
        force: bool = False,
    ) -> PdfDownload: ...


class DocumentParser(Protocol):
    """Minimum asynchronous document-parser contract."""

    async def parse(self, pdf_path: Path) -> ParsedDocument: ...


@dataclass(frozen=True, slots=True)
class _ProcessedPaper:
    paper: ArxivPaper
    parsed: ParsedDocument | None
    pdf_available: bool
    cache_hit: bool
    issues: list[IngestionIssue]


class IngestionService:
    """Coordinate source fetching, bounded PDF work, and transactional upserts."""

    def __init__(
        self,
        arxiv: ArxivSource,
        parser: DocumentParser,
        settings: IngestionSettings,
        category: str,
    ) -> None:
        self._arxiv = arxiv
        self._parser = parser
        self._settings = settings
        self._category = category

    async def run(
        self,
        session: Session,
        *,
        max_results: int | None = None,
        from_date: str | None = None,
        to_date: str | None = None,
        process_pdfs: bool = True,
        force_download: bool = False,
    ) -> IngestionReport:
        """Run one ingestion batch and continue across individual paper failures."""

        started_at = datetime.now(UTC)
        try:
            papers = await self._arxiv.fetch_papers(
                max_results=max_results,
                from_date=from_date,
                to_date=to_date,
            )
        except PaperforgeError as exc:
            raise IngestionPipelineError(f"metadata fetch failed: {exc}") from exc

        download_limit = asyncio.Semaphore(self._settings.max_concurrent_downloads)
        parse_limit = asyncio.Semaphore(self._settings.max_concurrent_parses)
        processed = await asyncio.gather(
            *(
                self._process_one(
                    paper,
                    process_pdfs=process_pdfs,
                    force_download=force_download,
                    download_limit=download_limit,
                    parse_limit=parse_limit,
                )
                for paper in papers
            )
        )

        repository = PaperRepository(session)
        created = 0
        updated = 0
        issues = [issue for item in processed for issue in item.issues]
        for item in processed:
            try:
                with session.begin_nested():
                    outcome = repository.upsert(self._to_upsert(item))
                if outcome.created:
                    created += 1
                else:
                    updated += 1
            except Exception as exc:
                issues.append(
                    IngestionIssue(
                        arxiv_id=item.paper.arxiv_id,
                        stage="database",
                        message=str(exc),
                    )
                )
                logger.exception(
                    "ingestion.paper_store_failed",
                    extra={"arxiv_id": item.paper.arxiv_id},
                )

        finished_at = datetime.now(UTC)
        report = IngestionReport(
            started_at=started_at,
            finished_at=finished_at,
            category=self._category,
            papers_fetched=len(papers),
            pdfs_available=sum(item.pdf_available for item in processed),
            pdf_cache_hits=sum(item.cache_hit for item in processed),
            pdfs_parsed=sum(item.parsed is not None for item in processed),
            papers_created=created,
            papers_updated=updated,
            issues=issues,
        )
        logger.info(
            "ingestion.completed",
            extra={
                "papers_fetched": report.papers_fetched,
                "papers_stored": report.papers_stored,
                "pdfs_parsed": report.pdfs_parsed,
                "issues": len(report.issues),
                "duration_seconds": (finished_at - started_at).total_seconds(),
            },
        )
        return report

    async def _process_one(
        self,
        paper: ArxivPaper,
        *,
        process_pdfs: bool,
        force_download: bool,
        download_limit: asyncio.Semaphore,
        parse_limit: asyncio.Semaphore,
    ) -> _ProcessedPaper:
        if not process_pdfs:
            return _ProcessedPaper(paper, None, False, False, [])

        issues: list[IngestionIssue] = []
        try:
            async with download_limit:
                downloaded = await self._arxiv.download_pdf(paper, force=force_download)
        except Exception as exc:
            issues.append(
                IngestionIssue(
                    arxiv_id=paper.arxiv_id,
                    stage="download",
                    message=str(exc),
                )
            )
            return _ProcessedPaper(paper, None, False, False, issues)

        try:
            async with parse_limit:
                parsed = await self._parser.parse(downloaded.path)
            return _ProcessedPaper(paper, parsed, True, downloaded.cache_hit, issues)
        except Exception as exc:
            issues.append(IngestionIssue(arxiv_id=paper.arxiv_id, stage="parse", message=str(exc)))
            return _ProcessedPaper(paper, None, True, downloaded.cache_hit, issues)

    @staticmethod
    def _to_upsert(item: _ProcessedPaper) -> PaperUpsert:
        paper = item.paper
        common: dict[str, Any] = {
            "arxiv_id": paper.arxiv_id,
            "title": paper.title,
            "authors": paper.authors,
            "abstract": paper.abstract,
            "categories": paper.categories,
            "published_date": paper.published_date,
            "pdf_url": paper.pdf_url,
        }
        if item.parsed is None:
            issue_metadata = (
                {"issues": [issue.model_dump() for issue in item.issues]} if item.issues else None
            )
            return PaperUpsert(**common, parser_metadata=issue_metadata)
        parsed = item.parsed
        return PaperUpsert(
            **common,
            raw_text=parsed.raw_text,
            sections=[section.model_dump() for section in parsed.sections],
            references=parsed.references,
            parser_used=parsed.parser_used,
            parser_metadata=parsed.parser_metadata,
            pdf_processed=True,
            pdf_processing_date=datetime.now(UTC),
        )
