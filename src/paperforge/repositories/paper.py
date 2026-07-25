"""Transactional repository for academic papers."""

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from paperforge.models.paper import Paper
from paperforge.schemas.papers import PaperUpsert


@dataclass(frozen=True, slots=True)
class UpsertOutcome:
    """Result of one metadata/content upsert."""

    paper: Paper
    created: bool


@dataclass(frozen=True, slots=True)
class PaperStats:
    """Current persistence statistics."""

    total: int
    processed: int
    with_text: int


class PaperRepository:
    """Persist and stream papers without owning transaction boundaries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_arxiv_id(self, arxiv_id: str) -> Paper | None:
        """Return one paper by its source identifier."""

        return self._session.scalar(select(Paper).where(Paper.arxiv_id == arxiv_id))

    def upsert(self, payload: PaperUpsert) -> UpsertOutcome:
        """Create or update metadata while preserving prior successful PDF content."""

        paper = self.get_by_arxiv_id(payload.arxiv_id)
        created = paper is None
        if paper is None:
            paper = Paper(
                arxiv_id=payload.arxiv_id,
                title=payload.title,
                authors=payload.authors,
                abstract=payload.abstract,
                categories=payload.categories,
                published_date=payload.published_date,
                pdf_url=payload.pdf_url,
                raw_text=payload.raw_text,
                sections=payload.sections,
                references=payload.references,
                parser_used=payload.parser_used,
                parser_metadata=payload.parser_metadata,
                pdf_processed=payload.pdf_processed,
                pdf_processing_date=payload.pdf_processing_date,
            )
            self._session.add(paper)
        else:
            paper.title = payload.title
            paper.authors = payload.authors
            paper.abstract = payload.abstract
            paper.categories = payload.categories
            paper.published_date = payload.published_date
            paper.pdf_url = payload.pdf_url
            if payload.pdf_processed:
                paper.raw_text = payload.raw_text
                paper.sections = payload.sections
                paper.references = payload.references
                paper.parser_used = payload.parser_used
                paper.parser_metadata = payload.parser_metadata
                paper.pdf_processed = True
                paper.pdf_processing_date = payload.pdf_processing_date
            elif not paper.pdf_processed and payload.parser_metadata is not None:
                paper.parser_metadata = payload.parser_metadata
        self._session.flush()
        return UpsertOutcome(paper=paper, created=created)

    def iter_for_search_index(
        self,
        *,
        batch_size: int,
        updated_since: datetime | None = None,
        processed_only: bool = False,
    ) -> Iterator[list[Paper]]:
        """Stream deterministic batches for OpenSearch synchronization."""

        statement: Select[tuple[Paper]] = select(Paper).order_by(Paper.updated_at, Paper.id)
        if updated_since is not None:
            statement = statement.where(Paper.updated_at >= updated_since)
        if processed_only:
            statement = statement.where(Paper.pdf_processed.is_(True))
        result = self._session.scalars(statement)
        for partition in result.partitions(batch_size):
            yield list(partition)

    def stats(self) -> PaperStats:
        """Return counts used by CLI and Airflow reporting."""

        total = self._session.scalar(select(func.count(Paper.id))) or 0
        processed = (
            self._session.scalar(select(func.count(Paper.id)).where(Paper.pdf_processed.is_(True)))
            or 0
        )
        with_text = (
            self._session.scalar(select(func.count(Paper.id)).where(Paper.raw_text.is_not(None)))
            or 0
        )
        return PaperStats(total=total, processed=processed, with_text=with_text)
