"""Pydantic schemas."""

from paperforge.schemas.papers import (
    ArxivPaper,
    DocumentSection,
    IngestionIssue,
    IngestionReport,
    PaperUpsert,
    ParsedDocument,
)
from paperforge.schemas.search import (
    BulkIndexResult,
    PaperSearchDocument,
    SearchHit,
    SearchIndexReport,
    SearchIndexStats,
    SearchRequest,
    SearchResponse,
    SearchSort,
)

__all__ = [
    "ArxivPaper",
    "BulkIndexResult",
    "DocumentSection",
    "IngestionIssue",
    "IngestionReport",
    "PaperSearchDocument",
    "PaperUpsert",
    "ParsedDocument",
    "SearchHit",
    "SearchIndexReport",
    "SearchIndexStats",
    "SearchRequest",
    "SearchResponse",
    "SearchSort",
]
