"""Typed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrozenSettingsModel(BaseModel):
    """Immutable base for nested settings sections."""

    model_config = ConfigDict(frozen=True)


class DatabaseSettings(FrozenSettingsModel):
    """PostgreSQL connection and pool settings."""

    url: str = "postgresql+psycopg://paperforge:paperforge-local-only@postgres:5432/paperforge"
    echo: bool = False
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    connect_timeout_seconds: int = Field(default=3, ge=1, le=60)

    @model_validator(mode="after")
    def validate_postgresql_url(self) -> Self:
        """Reject accidental SQLite or host-only database URLs."""

        if not self.url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("database URL must use PostgreSQL")
        return self


class OpenSearchSettings(FrozenSettingsModel):
    """OpenSearch connectivity, BM25 schema, and query limits."""

    enabled: bool = True
    required: bool = True
    url: str = "http://opensearch:9200"
    index_name: str = "paperforge-papers-bm25-v1"
    schema_version: int = Field(default=1, ge=1)
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)
    default_page_size: int = Field(default=10, ge=1, le=100)
    max_page_size: int = Field(default=50, ge=1, le=200)
    max_result_window: int = Field(default=10000, ge=100, le=100000)
    highlight_fragment_size: int = Field(default=180, ge=50, le=500)
    fuzzy_min_length: int = Field(default=5, ge=3, le=20)
    bulk_batch_size: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def validate_search_limits(self) -> Self:
        """Ensure defaults never exceed public query limits."""

        if self.default_page_size > self.max_page_size:
            raise ValueError("default_page_size cannot exceed max_page_size")
        return self


class RedisSettings(FrozenSettingsModel):
    """Redis connectivity and default cache settings."""

    enabled: bool = True
    required: bool = False
    url: str = "redis://redis:6379/0"
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    socket_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    default_ttl_seconds: int = Field(default=21600, ge=1)


class OllamaSettings(FrozenSettingsModel):
    """Ollama health adapter settings; generation is added in Week 5."""

    enabled: bool = False
    required: bool = False
    url: str = "http://ollama:11434"
    timeout_seconds: float = Field(default=3.0, gt=0, le=60)


class ArxivSettings(FrozenSettingsModel):
    """arXiv API and local PDF-cache settings."""

    base_url: str = "https://export.arxiv.org/api/query"
    category: str = "cs.AI"
    max_results: int = Field(default=15, ge=1, le=2000)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    rate_limit_seconds: float = Field(default=3.0, ge=3.0, le=60)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=2.0, gt=0, le=60)
    user_agent: str = "paperforge/0.4.0"
    pdf_cache_dir: Path = Path("/workspace/data/arxiv_pdfs")
    max_pdf_download_mb: int = Field(default=25, ge=1, le=200)


class DocumentParserSettings(FrozenSettingsModel):
    """Docling parsing limits and feature switches."""

    enabled: bool = True
    max_pages: int = Field(default=30, ge=1, le=500)
    max_file_size_mb: int = Field(default=20, ge=1, le=200)
    do_ocr: bool = False
    do_table_structure: bool = True


class IngestionSettings(FrozenSettingsModel):
    """Concurrency and retention settings for the ingestion pipeline."""

    max_concurrent_downloads: int = Field(default=2, ge=1, le=10)
    max_concurrent_parses: int = Field(default=1, ge=1, le=4)
    pdf_retention_days: int = Field(default=30, ge=1, le=365)


class Settings(BaseSettings):
    """Environment-driven settings for Paperforge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PAPERFORGE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    service_name: str = "paperforge-api"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = True

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    document_parser: DocumentParserSettings = Field(default_factory=DocumentParserSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings object per process."""

    return Settings()
