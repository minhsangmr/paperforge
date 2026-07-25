"""Schemas for Week 4 chunking, embeddings, and hybrid retrieval."""

from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SearchMode = Literal["auto", "bm25", "vector", "hybrid"]
ResolvedSearchMode = Literal["bm25", "vector", "hybrid"]


class FrozenSchema(BaseModel):
    """Immutable schema base."""

    model_config = ConfigDict(frozen=True)


class TextChunk(FrozenSchema):
    """One deterministic, section-aware text chunk."""

    chunk_id: str
    chunk_index: int
    section_title: str
    section_level: int = Field(default=1, ge=1, le=6)
    text: str
    word_count: int = Field(ge=1)


class HybridChunkDocument(FrozenSchema):
    """Chunk-level document persisted in the Week 4 OpenSearch index."""

    chunk_id: str
    chunk_index: int
    paper_id: str
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    section_title: str
    section_level: int
    chunk_text: str
    chunk_word_count: int
    has_embedding: bool
    embedding_model: str | None = None
    embedding: list[float] | None = None
    updated_at: datetime


class HybridSearchRequest(BaseModel):
    """Validated request shared by the hybrid API and CLI."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=500)
    mode: SearchMode = "auto"
    categories: list[str] = Field(default_factory=list)
    published_from: date | None = None
    published_to: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=200)

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


class HybridSearchHit(FrozenSchema):
    """One chunk-level search hit with denormalized paper metadata."""

    chunk_id: str
    chunk_index: int
    arxiv_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published_date: datetime
    pdf_url: str
    section_title: str
    chunk_text: str
    score: float | None = None
    highlights: dict[str, list[str]] = Field(default_factory=dict)


class HybridSearchResponse(FrozenSchema):
    """Paginated unified retrieval response."""

    query: str
    requested_mode: SearchMode
    search_mode: ResolvedSearchMode
    embeddings_used: bool
    total: int
    page: int
    page_size: int
    took_ms: int
    hits: list[HybridSearchHit]


class HybridBulkIndexResult(FrozenSchema):
    """Outcome of one chunk bulk-index request."""

    attempted: int
    indexed: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class HybridIndexReport(FrozenSchema):
    """Summary of one PostgreSQL-to-hybrid-index synchronization run."""

    index_name: str
    rebuilt: bool
    embeddings_enabled: bool
    papers_attempted: int
    papers_indexed: int
    papers_skipped: int
    chunks_created: int
    chunks_indexed: int
    failed: int
    errors: list[str] = Field(default_factory=list)


class HybridIndexStats(FrozenSchema):
    """Hybrid-index health and size information."""

    index_name: str
    search_pipeline: str
    exists: bool
    schema_version: int | None = None
    document_count: int = 0
    embedded_document_count: int = 0
    unique_paper_count: int = 0
    deleted_count: int = 0
    size_in_bytes: int = 0
