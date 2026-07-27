"""Typed state shared by LangGraph Week 7 nodes."""

from operator import add
from typing import Annotated, Literal, TypedDict

from paperforge.schemas.agentic import AgenticReasoningStep, DocumentGrade, GuardrailResult
from paperforge.schemas.hybrid_search import HybridSearchHit, ResolvedSearchMode
from paperforge.schemas.rag import OllamaUsage, RAGSource

AgentRoute = Literal["retrieve", "generate", "rewrite", "out_of_scope", "no_context"]


class AgentState(TypedDict, total=False):
    original_query: str
    active_query: str
    model: str
    top_k: int
    use_hybrid: bool
    categories: list[str]
    max_retrieval_attempts: int
    retrieval_attempts: int
    guardrail: GuardrailResult
    route: AgentRoute
    retrieved_hits: list[HybridSearchHit]
    relevant_hits: list[HybridSearchHit]
    grades: list[DocumentGrade]
    search_mode: ResolvedSearchMode
    rewritten_query: str | None
    answer: str
    sources: list[RAGSource]
    usage: OllamaUsage
    status: Literal["completed", "out_of_scope", "no_context"]
    reasoning_steps: Annotated[list[AgenticReasoningStep], add]
