"""Public schemas for the Week 7 bounded Agentic RAG workflow."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from paperforge.schemas.hybrid_search import ResolvedSearchMode
from paperforge.schemas.rag import OllamaUsage, RAGSource


class AgenticRAGRequest(BaseModel):
    """Question and runtime controls for the agentic graph."""

    model_config = ConfigDict(frozen=True)

    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=3, ge=1, le=10)
    use_hybrid: bool = True
    model: str | None = Field(default=None, min_length=1, max_length=120)
    categories: list[str] = Field(default_factory=list)
    user_id: str | None = Field(default=None, min_length=1, max_length=120)
    session_id: str | None = Field(default=None, min_length=1, max_length=120)
    max_retrieval_attempts: int | None = Field(default=None, ge=1, le=5)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query cannot be blank")
        return normalized

    @field_validator("model", "user_id", "session_id")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("optional text values cannot be blank")
        return normalized

    @field_validator("categories")
    @classmethod
    def normalize_categories(cls, values: list[str]) -> list[str]:
        return list(dict.fromkeys(value.strip() for value in values if value.strip()))


class GuardrailResult(BaseModel):
    """Domain-scope decision produced before retrieval."""

    model_config = ConfigDict(frozen=True)

    score: int = Field(ge=0, le=100)
    reason: str
    accepted: bool


class DocumentGrade(BaseModel):
    """Auditable relevance decision for one retrieved chunk."""

    model_config = ConfigDict(frozen=True)

    chunk_id: str
    relevant: bool
    reason: str = ""


class AgenticReasoningStep(BaseModel):
    """Operational workflow summary; never hidden model chain-of-thought."""

    model_config = ConfigDict(frozen=True)

    step: Literal[
        "guardrail",
        "retrieve",
        "grade_documents",
        "rewrite_query",
        "generate_answer",
        "out_of_scope",
        "no_context",
    ]
    summary: str
    metadata: dict[str, object] = Field(default_factory=dict)


class AgenticRAGResponse(BaseModel):
    """Final bounded-workflow result returned by API and Telegram."""

    model_config = ConfigDict(frozen=True)

    query: str
    answer: str
    sources: list[RAGSource]
    chunks_used: int = Field(ge=0)
    search_mode: ResolvedSearchMode
    model: str
    usage: OllamaUsage = Field(default_factory=OllamaUsage)
    trace_id: str | None = None
    reasoning_steps: list[AgenticReasoningStep]
    retrieval_attempts: int = Field(ge=0)
    rewritten_query: str | None = None
    guardrail: GuardrailResult
    status: Literal["completed", "out_of_scope", "no_context"]
