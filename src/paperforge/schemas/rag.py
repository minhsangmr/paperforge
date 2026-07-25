"""Schemas for Week 5 retrieval-augmented generation."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from paperforge.schemas.hybrid_search import ResolvedSearchMode


class RAGRequest(BaseModel):
    """Question-answering request compatible with the original Week 5 API."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)
    use_hybrid: bool = True
    model: str | None = Field(default=None, min_length=1, max_length=120)
    categories: list[str] = Field(default_factory=list)
    user_id: str | None = Field(default=None, min_length=1, max_length=120)
    session_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        """Trim whitespace and reject blank questions."""

        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        """Normalize an optional Ollama model override."""

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("model cannot be blank")
        return normalized

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, values: list[str]) -> list[str]:
        """Remove blank and duplicate arXiv categories while preserving order."""

        seen: set[str] = set()
        normalized: list[str] = []
        for value in values:
            category = value.strip()
            if category and category not in seen:
                seen.add(category)
                normalized.append(category)
        return normalized

    @field_validator("user_id", "session_id")
    @classmethod
    def normalize_trace_identifier(cls, value: str | None) -> str | None:
        """Normalize optional correlation identifiers used only for tracing."""

        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("trace identifiers cannot be blank")
        return normalized


class RAGSource(BaseModel):
    """One retrieved chunk exposed as a citeable answer source."""

    model_config = ConfigDict(frozen=True)

    citation: str
    arxiv_id: str
    title: str
    pdf_url: str
    section_title: str
    chunk_id: str


class OllamaUsage(BaseModel):
    """Normalized token and latency metadata returned by Ollama."""

    model_config = ConfigDict(frozen=True)

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)
    latency_ms: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def fill_total(self) -> Self:
        """Derive total tokens when Ollama only returns separate counts."""

        expected = self.prompt_tokens + self.completion_tokens
        if self.total_tokens == 0 and expected:
            object.__setattr__(self, "total_tokens", expected)
        return self


class RAGResponse(BaseModel):
    """Complete non-streaming answer with retrieval and generation metadata."""

    model_config = ConfigDict(frozen=True)

    query: str
    answer: str
    sources: list[RAGSource]
    chunks_used: int = Field(ge=0)
    search_mode: ResolvedSearchMode
    model: str
    usage: OllamaUsage = Field(default_factory=OllamaUsage)
    cache_hit: bool = False
    trace_id: str | None = None


class RAGStreamEvent(BaseModel):
    """Typed payload serialized into one Server-Sent Event."""

    model_config = ConfigDict(frozen=True)

    event: Literal["metadata", "token", "done", "error"]
    data: dict[str, object]
