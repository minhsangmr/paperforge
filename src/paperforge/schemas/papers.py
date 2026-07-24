"""Schemas shared by arXiv ingestion and paper persistence."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FrozenSchema(BaseModel):
    """Immutable schema base."""

    model_config = ConfigDict(frozen=True)


class ArxivPaper(FrozenSchema):
    """Normalized metadata parsed from one arXiv Atom entry."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str


class DocumentSection(FrozenSchema):
    """One heading-delimited document section."""

    title: str
    content: str
    level: int = Field(default=1, ge=1, le=6)


class ParsedDocument(FrozenSchema):
    """Structured content returned by a document parser."""

    raw_text: str
    sections: list[DocumentSection]
    references: list[dict[str, Any]] = Field(default_factory=list)
    parser_used: str
    parser_metadata: dict[str, Any] = Field(default_factory=dict)


class PaperUpsert(FrozenSchema):
    """Metadata plus optional parsed content to persist atomically."""

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    raw_text: str | None = None
    sections: list[dict[str, Any]] | None = None
    references: list[dict[str, Any]] | None = None
    parser_used: str | None = None
    parser_metadata: dict[str, Any] | None = None
    pdf_processed: bool = False
    pdf_processing_date: datetime | None = None


class IngestionIssue(FrozenSchema):
    """One recoverable per-paper failure."""

    arxiv_id: str | None
    stage: str
    message: str


class IngestionReport(FrozenSchema):
    """Machine-readable summary emitted by the CLI and Airflow task."""

    started_at: datetime
    finished_at: datetime
    category: str
    papers_fetched: int = 0
    pdfs_available: int = 0
    pdf_cache_hits: int = 0
    pdfs_parsed: int = 0
    papers_created: int = 0
    papers_updated: int = 0
    issues: list[IngestionIssue] = Field(default_factory=list)

    @property
    def papers_stored(self) -> int:
        """Return the total number of successful database upserts."""

        return self.papers_created + self.papers_updated
