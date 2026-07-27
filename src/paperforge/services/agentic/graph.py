"""Bounded LangGraph workflow for Week 7 Agentic RAG."""

import logging
import re
from collections.abc import Awaitable
from typing import Literal, Protocol, cast

from langgraph.graph import END, START, StateGraph

from paperforge.core.config import AgenticSettings, RAGSettings
from paperforge.schemas.agentic import AgenticReasoningStep, DocumentGrade, GuardrailResult
from paperforge.schemas.hybrid_search import HybridSearchHit, HybridSearchRequest
from paperforge.schemas.rag import OllamaUsage
from paperforge.services.agentic.json_utils import parse_json_object
from paperforge.services.agentic.prompts import GRADE_PROMPT, GUARDRAIL_PROMPT, REWRITE_PROMPT
from paperforge.services.agentic.state import AgentRoute, AgentState
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.ollama.prompts import RAGPromptBuilder

logger = logging.getLogger(__name__)
_TOKEN_RE = re.compile(r"[a-zA-Z][a-zA-Z0-9_-]{2,}")
_DOMAIN_TERMS = {
    "ai",
    "algorithm",
    "artificial",
    "attention",
    "bert",
    "computer",
    "data",
    "deep",
    "embedding",
    "information",
    "language",
    "learning",
    "machine",
    "model",
    "neural",
    "paper",
    "rag",
    "research",
    "retrieval",
    "software",
    "transformer",
    "vector",
    "vision",
}


class CompiledAgentGraph(Protocol):
    """Minimal interface required from a compiled LangGraph workflow."""

    def ainvoke(self, input: AgentState) -> Awaitable[object]:
        """Invoke the compiled workflow asynchronously."""
        ...


class AgenticGraph:
    """Compile and run deterministic plus LLM-driven nodes with a hard retry bound."""

    def __init__(
        self,
        retrieval: HybridSearchService,
        ollama: OllamaClient,
        settings: AgenticSettings,
        rag_settings: RAGSettings,
    ) -> None:
        self._retrieval = retrieval
        self._ollama = ollama
        self._settings = settings
        self._prompt_builder = RAGPromptBuilder(
            max_context_characters=rag_settings.max_context_characters,
            max_answer_words=rag_settings.max_answer_words,
        )
        self.graph = self._build()

    def _build(self) -> CompiledAgentGraph:
        builder = StateGraph(AgentState)
        builder.add_node("guardrail", self._guardrail)
        builder.add_node("retrieve", self._retrieve)
        builder.add_node("grade_documents", self._grade_documents)
        builder.add_node("rewrite_query", self._rewrite_query)
        builder.add_node("generate_answer", self._generate_answer)
        builder.add_node("out_of_scope", self._out_of_scope)
        builder.add_node("no_context", self._no_context)
        builder.add_edge(START, "guardrail")
        builder.add_conditional_edges(
            "guardrail",
            self._route_after_guardrail,
            {"retrieve": "retrieve", "out_of_scope": "out_of_scope"},
        )
        builder.add_edge("retrieve", "grade_documents")
        builder.add_conditional_edges(
            "grade_documents",
            self._route_after_grading,
            {"generate": "generate_answer", "rewrite": "rewrite_query", "no_context": "no_context"},
        )
        builder.add_edge("rewrite_query", "retrieve")
        builder.add_edge("generate_answer", END)
        builder.add_edge("out_of_scope", END)
        builder.add_edge("no_context", END)
        return cast(CompiledAgentGraph, builder.compile())

    async def invoke(self, state: AgentState) -> AgentState:
        return cast(AgentState, await self.graph.ainvoke(state))

    async def _guardrail(self, state: AgentState) -> dict[str, object]:
        query = state["original_query"]
        model = state["model"]
        try:
            raw, _ = await self._ollama.generate(
                prompt=GUARDRAIL_PROMPT.format(question=query), model=model
            )
            data = parse_json_object(raw)
            score = max(0, min(100, int(data.get("score", 0))))
            reason = str(data.get("reason", "No reason supplied")).strip()
        except Exception as exc:
            score = self._fallback_guardrail_score(query)
            reason = f"Deterministic fallback after guardrail model failure: {type(exc).__name__}"
            logger.warning("agentic.guardrail_fallback", exc_info=True)
        accepted = score >= self._settings.guardrail_threshold
        route: AgentRoute = "retrieve" if accepted else "out_of_scope"
        result = GuardrailResult(score=score, reason=reason, accepted=accepted)
        return {
            "guardrail": result,
            "route": route,
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="guardrail",
                    summary=(
                        "Accepted as academic CS research."
                        if accepted
                        else "Rejected as outside the indexed research scope."
                    ),
                    metadata={"score": score, "threshold": self._settings.guardrail_threshold},
                )
            ],
        }

    async def _retrieve(self, state: AgentState) -> dict[str, object]:
        attempts = state.get("retrieval_attempts", 0) + 1
        mode: Literal["auto", "bm25"] = "auto" if state["use_hybrid"] else "bm25"
        response = await self._retrieval.search(
            HybridSearchRequest(
                query=state["active_query"],
                mode=mode,
                categories=state["categories"],
                page=1,
                page_size=state["top_k"],
            )
        )
        return {
            "retrieval_attempts": attempts,
            "retrieved_hits": response.hits,
            "search_mode": response.search_mode,
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="retrieve",
                    summary=f"Retrieved {len(response.hits)} candidate chunks.",
                    metadata={
                        "attempt": attempts,
                        "query": state["active_query"],
                        "mode": response.search_mode,
                    },
                )
            ],
        }

    async def _grade_documents(self, state: AgentState) -> dict[str, object]:
        hits = state.get("retrieved_hits", [])
        if not hits:
            return {
                "relevant_hits": [],
                "grades": [],
                "route": self._retry_route(state),
                "reasoning_steps": [
                    AgenticReasoningStep(
                        step="grade_documents",
                        summary="No chunks were available to grade.",
                        metadata={"relevant": 0, "candidates": 0},
                    )
                ],
            }
        compact = "\n\n".join(
            (
                f"ID: {hit.chunk_id}\nTitle: {hit.title}\n"
                f"Section: {hit.section_title}\nText: {hit.chunk_text[:1600]}"
            )
            for hit in hits
        )[: self._settings.max_grading_characters]
        relevant_ids: set[str]
        reason: str
        try:
            raw, _ = await self._ollama.generate(
                prompt=GRADE_PROMPT.format(question=state["original_query"], chunks=compact),
                model=state["model"],
            )
            data = parse_json_object(raw)
            values = data.get("relevant_chunk_ids", [])
            relevant_ids = {str(item) for item in values} if isinstance(values, list) else set()
            reason = str(data.get("reason", ""))
        except Exception:
            relevant_ids = self._fallback_relevant_ids(state["original_query"], hits)
            reason = "Deterministic token-overlap fallback was used."
            logger.warning("agentic.grading_fallback", exc_info=True)
        relevant = [hit for hit in hits if hit.chunk_id in relevant_ids]
        grades = [
            DocumentGrade(
                chunk_id=hit.chunk_id, relevant=hit.chunk_id in relevant_ids, reason=reason
            )
            for hit in hits
        ]
        return {
            "relevant_hits": relevant,
            "grades": grades,
            "route": "generate" if relevant else self._retry_route(state),
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="grade_documents",
                    summary=f"Selected {len(relevant)} of {len(hits)} chunks as relevant.",
                    metadata={"relevant": len(relevant), "candidates": len(hits)},
                )
            ],
        }

    async def _rewrite_query(self, state: AgentState) -> dict[str, object]:
        raw, _ = await self._ollama.generate(
            prompt=REWRITE_PROMPT.format(
                question=state["original_query"], active_query=state["active_query"]
            ),
            model=state["model"],
        )
        rewritten = raw.strip().strip('"')[:500]
        if not rewritten:
            rewritten = f"{state['original_query']} academic research papers"
        return {
            "active_query": rewritten,
            "rewritten_query": rewritten,
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="rewrite_query",
                    summary="Rewrote the search query for another bounded retrieval attempt.",
                    metadata={"attempt": state.get("retrieval_attempts", 0) + 1},
                )
            ],
        }

    async def _generate_answer(self, state: AgentState) -> dict[str, object]:
        bundle = self._prompt_builder.build(state["original_query"], state["relevant_hits"])
        answer, usage = await self._ollama.generate(prompt=bundle.prompt, model=state["model"])
        return {
            "answer": answer,
            "sources": bundle.sources,
            "usage": usage,
            "status": "completed",
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="generate_answer",
                    summary="Generated a grounded answer from the graded chunks.",
                    metadata={"sources": len(bundle.sources)},
                )
            ],
        }

    async def _out_of_scope(self, state: AgentState) -> dict[str, object]:
        return {
            "answer": self._settings.out_of_scope_answer,
            "sources": [],
            "usage": OllamaUsage(),
            "status": "out_of_scope",
            "search_mode": "bm25",
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="out_of_scope",
                    summary="Returned a scope-safe response without retrieval.",
                    metadata={},
                )
            ],
        }

    async def _no_context(self, state: AgentState) -> dict[str, object]:
        return {
            "answer": self._settings.no_context_answer,
            "sources": [],
            "usage": OllamaUsage(),
            "status": "no_context",
            "search_mode": state.get("search_mode", "bm25"),
            "reasoning_steps": [
                AgenticReasoningStep(
                    step="no_context",
                    summary="Stopped after the configured retrieval-attempt limit.",
                    metadata={"attempts": state.get("retrieval_attempts", 0)},
                )
            ],
        }

    @staticmethod
    def _route_after_guardrail(state: AgentState) -> AgentRoute:
        return state.get("route", "out_of_scope")

    @staticmethod
    def _route_after_grading(state: AgentState) -> AgentRoute:
        return state.get("route", "no_context")

    @staticmethod
    def _retry_route(state: AgentState) -> AgentRoute:
        return (
            "rewrite"
            if state.get("retrieval_attempts", 0) < state["max_retrieval_attempts"]
            else "no_context"
        )

    @staticmethod
    def _fallback_guardrail_score(query: str) -> int:
        tokens = {token.lower() for token in _TOKEN_RE.findall(query)}
        return 75 if tokens & _DOMAIN_TERMS else 25

    @staticmethod
    def _fallback_relevant_ids(query: str, hits: list[HybridSearchHit]) -> set[str]:
        query_tokens = {token.lower() for token in _TOKEN_RE.findall(query)}
        selected = {
            hit.chunk_id
            for hit in hits
            if query_tokens
            & {
                token.lower()
                for token in _TOKEN_RE.findall(f"{hit.title} {hit.section_title} {hit.chunk_text}")
            }
        }
        if not selected and hits:
            selected.add(hits[0].chunk_id)
        return selected
