"""Typed application configuration."""

from functools import lru_cache
from pathlib import Path
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
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


class RAGCacheSettings(FrozenSettingsModel):
    """Exact-match response cache behavior."""

    enabled: bool = True
    namespace: str = "paperforge:rag-cache:v1"
    ttl_seconds: int = Field(default=86400, ge=60, le=604800)
    response_schema_version: int = Field(default=1, ge=1)
    stream_chunk_characters: int = Field(default=96, ge=16, le=1000)
    cache_empty_answers: bool = False

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        normalized = value.strip().strip(":")
        if not normalized:
            raise ValueError("cache namespace cannot be blank")
        return normalized


class LangfuseSettings(FrozenSettingsModel):
    """Optional Langfuse tracing and feedback configuration."""

    enabled: bool = False
    required: bool = False
    base_url: str = "http://langfuse-web:3000"
    public_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    timeout_seconds: int = Field(default=5, ge=1, le=60)
    flush_at: int = Field(default=64, ge=1, le=1000)
    flush_interval_seconds: float = Field(default=5.0, gt=0, le=60)
    sample_rate: float = Field(default=1.0, ge=0, le=1)
    tracing_environment: str = "development"
    release: str = "1.0.0"
    capture_content: bool = False
    score_name: str = "user-feedback"

    @field_validator("public_key", "secret_key", mode="before")
    @classmethod
    def blank_secret_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def configured(self) -> bool:
        """Return true only when both SDK credentials are present."""

        return self.public_key is not None and self.secret_key is not None


class OllamaSettings(FrozenSettingsModel):
    """Ollama health, generation, and local-model settings."""

    enabled: bool = False
    required: bool = False
    url: str = "http://ollama:11434"
    health_timeout_seconds: float = Field(default=3.0, gt=0, le=60)
    request_timeout_seconds: float = Field(default=120.0, gt=0, le=600)
    default_model: str = "llama3.2:1b"
    temperature: float = Field(default=0.2, ge=0, le=2)
    top_p: float = Field(default=0.9, gt=0, le=1)
    max_output_tokens: int = Field(default=512, ge=32, le=8192)
    keep_alive: str = "10m"


class RAGSettings(FrozenSettingsModel):
    """Grounded prompt and retrieval limits."""

    default_top_k: int = Field(default=3, ge=1, le=10)
    max_top_k: int = Field(default=10, ge=1, le=20)
    default_model: str = "llama3.2:1b"
    max_context_characters: int = Field(default=24000, ge=1000, le=200000)
    max_answer_words: int = Field(default=300, ge=50, le=2000)
    no_context_answer: str = (
        "I could not find enough relevant information in the indexed papers "
        "to answer that question."
    )

    @model_validator(mode="after")
    def validate_top_k(self) -> Self:
        """Keep the default retrieval count within the public limit."""

        if self.default_top_k > self.max_top_k:
            raise ValueError("default_top_k cannot exceed max_top_k")
        return self


class UISettings(FrozenSettingsModel):
    """Containerized Gradio client settings."""

    enabled: bool = True
    api_base_url: str = "http://api:8000/api/v1"
    host: str = "0.0.0.0"
    port: int = Field(default=7861, ge=1, le=65535)


class ArxivSettings(FrozenSettingsModel):
    """arXiv API and local PDF-cache settings."""

    base_url: str = "https://export.arxiv.org/api/query"
    category: str = "cs.AI"
    max_results: int = Field(default=15, ge=1, le=2000)
    request_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    rate_limit_seconds: float = Field(default=3.0, ge=3.0, le=60)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=2.0, gt=0, le=60)
    user_agent: str = "paperforge/1.0.0"
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


class ChunkingSettings(FrozenSettingsModel):
    """Deterministic section-aware chunking limits."""

    chunk_size_words: int = Field(default=600, ge=2, le=2000)
    overlap_words: int = Field(default=100, ge=0, le=500)
    min_chunk_words: int = Field(default=80, ge=1, le=500)
    excluded_section_titles: list[str] = Field(
        default_factory=lambda: [
            "references",
            "bibliography",
            "acknowledgements",
            "acknowledgments",
        ]
    )

    @model_validator(mode="after")
    def validate_windows(self) -> Self:
        """Ensure overlap advances and the minimum fits in a target chunk."""

        if self.overlap_words >= self.chunk_size_words:
            raise ValueError("overlap_words must be smaller than chunk_size_words")
        if self.min_chunk_words > self.chunk_size_words:
            raise ValueError("min_chunk_words cannot exceed chunk_size_words")
        return self


class EmbeddingSettings(FrozenSettingsModel):
    """Jina retrieval-embedding configuration."""

    enabled: bool = True
    required: bool = False
    api_key: SecretStr | None = None
    base_url: str = "https://api.jina.ai/v1/embeddings"
    model: str = "jina-embeddings-v5-text-small"
    dimensions: int = Field(default=1024, ge=1, le=4096)
    timeout_seconds: float = Field(default=30.0, gt=0, le=180)
    batch_size: int = Field(default=32, ge=1, le=100)
    max_retries: int = Field(default=3, ge=1, le=10)
    retry_backoff_seconds: float = Field(default=1.0, gt=0, le=60)
    max_input_characters: int = Field(default=24000, ge=1000, le=100000)

    @field_validator("api_key", mode="before")
    @classmethod
    def blank_api_key_is_none(cls, value: object) -> object:
        """Treat an empty environment variable as an unconfigured API key."""

        if isinstance(value, str) and not value.strip():
            return None
        return value


class HybridSearchSettings(FrozenSettingsModel):
    """Chunk-index, vector-search, and RRF tuning settings."""

    enabled: bool = True
    index_name: str = "paperforge-chunks-hybrid-v1"
    schema_version: int = Field(default=1, ge=1)
    search_pipeline: str = "paperforge-hybrid-rrf-v1"
    embedding_field: str = "embedding"
    default_page_size: int = Field(default=10, ge=1, le=100)
    max_page_size: int = Field(default=50, ge=1, le=200)
    max_result_window: int = Field(default=10000, ge=100, le=100000)
    highlight_fragment_size: int = Field(default=220, ge=50, le=500)
    bulk_batch_size: int = Field(default=25, ge=1, le=500)
    candidate_multiplier: int = Field(default=4, ge=1, le=20)
    max_candidate_count: int = Field(default=200, ge=10, le=10000)
    rrf_rank_constant: int = Field(default=60, ge=1, le=1000)
    bm25_weight: float = Field(default=0.5, ge=0, le=1)
    vector_weight: float = Field(default=0.5, ge=0, le=1)
    hnsw_m: int = Field(default=16, ge=2, le=100)
    hnsw_ef_construction: int = Field(default=100, ge=8, le=1000)

    @model_validator(mode="after")
    def validate_hybrid_limits(self) -> Self:
        """Validate public limits and RRF weights."""

        if self.default_page_size > self.max_page_size:
            raise ValueError("default_page_size cannot exceed max_page_size")
        if abs((self.bm25_weight + self.vector_weight) - 1.0) > 1e-9:
            raise ValueError("bm25_weight and vector_weight must sum to 1.0")
        return self


class AgenticSettings(FrozenSettingsModel):
    """Bounded LangGraph decision and retry settings."""

    enabled: bool = True
    default_model: str = "llama3.2:1b"
    default_top_k: int = Field(default=3, ge=1, le=10)
    max_top_k: int = Field(default=10, ge=1, le=20)
    max_retrieval_attempts: int = Field(default=2, ge=1, le=5)
    guardrail_threshold: int = Field(default=60, ge=0, le=100)
    max_grading_characters: int = Field(default=12000, ge=1000, le=50000)
    out_of_scope_answer: str = (
        "I can help with academic computer-science and AI research questions. "
        "Please ask about a technical topic or indexed research papers."
    )
    no_context_answer: str = (
        "I could not find sufficiently relevant indexed paper excerpts after the "
        "configured retrieval attempts. Try a more specific technical question."
    )

    @model_validator(mode="after")
    def validate_top_k(self) -> Self:
        if self.default_top_k > self.max_top_k:
            raise ValueError("default_top_k cannot exceed max_top_k")
        return self


class TelegramSettings(FrozenSettingsModel):
    """Separate Telegram polling-process settings."""

    enabled: bool = False
    bot_token: SecretStr | None = None
    api_base_url: str = "http://api:8000/api/v1"
    request_timeout_seconds: float = Field(default=180.0, gt=0, le=600)
    max_message_characters: int = Field(default=3800, ge=500, le=4096)
    allowed_user_ids: list[int] = Field(default_factory=list)
    drop_pending_updates: bool = True

    @field_validator("bot_token", mode="before")
    @classmethod
    def blank_token_is_none(cls, value: object) -> object:
        if isinstance(value, SecretStr):
            return None if not value.get_secret_value().strip() else value

        if isinstance(value, str):
            return None if not value.strip() else value

        return value

    @property
    def configured(self) -> bool:
        return self.enabled and self.bot_token is not None


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
    rag_cache: RAGCacheSettings = Field(default_factory=RAGCacheSettings)
    langfuse: LangfuseSettings = Field(default_factory=LangfuseSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)
    rag: RAGSettings = Field(default_factory=RAGSettings)
    agentic: AgenticSettings = Field(default_factory=AgenticSettings)
    telegram: TelegramSettings = Field(default_factory=TelegramSettings)
    ui: UISettings = Field(default_factory=UISettings)
    arxiv: ArxivSettings = Field(default_factory=ArxivSettings)
    document_parser: DocumentParserSettings = Field(default_factory=DocumentParserSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    chunking: ChunkingSettings = Field(default_factory=ChunkingSettings)
    embeddings: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    hybrid_search: HybridSearchSettings = Field(default_factory=HybridSearchSettings)


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings object per process."""

    return Settings()
