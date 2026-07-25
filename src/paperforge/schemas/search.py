"""Schemas for BM25 indexing and search APIs."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SearchSort = Literal["relevance", "published_desc", "published_asc"]


class SearchRequest(BaseModel):
    """Validated BM25 search request shared by GET, POST, and CLI."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=500)
    categories: list[str] = Field(default_factory=list, max_length=20)
    published_from: date | None = None
    published_to: date | None = None
    processed_only: bool = False
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)
    sort: SearchSort = "relevance"

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        """Trim surrounding whitespace and reject empty queries."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        """Reject inverted publication-date filters."""

        if (
            self.published_from is not None
            and self.published_to is not None
            and self.published_from > self.published_to
        ):
            raise ValueError("published_from cannot be after published_to")
        return self

    @property
    def offset(self) -> int:
        """Return the OpenSearch result offset."""

        return (self.page - 1) * self.page_size


class PaperSearchDocument(BaseModel):
    """One PostgreSQL paper projected into the Week 3 search index."""

    model_config = ConfigDict(frozen=True)

    id: str
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    raw_text: str = ""
    pdf_processed: bool
    created_at: datetime
    updated_at: datetime


class SearchHit(BaseModel):
    """One ranked paper returned by OpenSearch."""

    model_config = ConfigDict(frozen=True)

    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    pdf_processed: bool
    score: float | None = None
    highlights: dict[str, list[str]] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    """Paginated BM25 search response."""

    model_config = ConfigDict(frozen=True)

    query: str
    total: int
    page: int
    page_size: int
    took_ms: int
    hits: list[SearchHit]


class BulkIndexResult(BaseModel):
    """Outcome of one OpenSearch bulk request."""

    model_config = ConfigDict(frozen=True)

    attempted: int
    indexed: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class SearchIndexReport(BaseModel):
    """Summary of one PostgreSQL-to-OpenSearch synchronization run."""

    model_config = ConfigDict(frozen=True)

    index_name: str
    rebuilt: bool
    batches: int
    attempted: int
    indexed: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class SearchIndexStats(BaseModel):
    """Search-index health and size information."""

    model_config = ConfigDict(frozen=True)

    index_name: str
    exists: bool
    schema_version: int | None = None
    document_count: int = 0
    deleted_count: int = 0
    size_in_bytes: int = 0
