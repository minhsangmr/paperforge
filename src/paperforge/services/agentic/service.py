"""Application service around the bounded LangGraph workflow."""

from paperforge.core.config import AgenticSettings, RAGSettings
from paperforge.schemas.agentic import AgenticRAGRequest, AgenticRAGResponse, GuardrailResult
from paperforge.schemas.rag import OllamaUsage
from paperforge.services.agentic.graph import AgenticGraph
from paperforge.services.agentic.state import AgentState
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.observability.langfuse import LangfuseObservability
from paperforge.services.ollama.client import OllamaClient


class AgenticRAGService:
    """Execute and trace one complete bounded agent workflow."""

    def __init__(
        self,
        retrieval: HybridSearchService,
        ollama: OllamaClient,
        settings: AgenticSettings,
        rag_settings: RAGSettings,
        observability: LangfuseObservability,
    ) -> None:
        self._settings = settings
        self._observability = observability
        self._graph = AgenticGraph(retrieval, ollama, settings, rag_settings)

    async def answer(self, request: AgenticRAGRequest) -> AgenticRAGResponse:
        model = request.model or self._settings.default_model
        max_attempts = request.max_retrieval_attempts or self._settings.max_retrieval_attempts
        with self._observability.trace_agentic(request) as trace:
            try:
                with trace.observe(
                    name="agentic-workflow",
                    as_type="agent",
                    input_data=self._observability.content(request.query, label="query"),
                    metadata={
                        "top_k": request.top_k,
                        "use_hybrid": request.use_hybrid,
                        "max_retrieval_attempts": max_attempts,
                    },
                ) as workflow_observation:
                    state = await self._graph.invoke(
                        AgentState(
                            original_query=request.query,
                            active_query=request.query,
                            model=model,
                            top_k=request.top_k,
                            use_hybrid=request.use_hybrid,
                            categories=request.categories,
                            max_retrieval_attempts=max_attempts,
                            retrieval_attempts=0,
                            relevant_hits=[],
                            reasoning_steps=[],
                            rewritten_query=None,
                        )
                    )
                    workflow_observation.update(
                        output={
                            "status": state.get("status", "no_context"),
                            "retrieval_attempts": state.get("retrieval_attempts", 0),
                            "relevant_chunks": len(state.get("relevant_hits", [])),
                        }
                    )
                guardrail = state.get("guardrail") or GuardrailResult(
                    score=0, reason="guardrail result missing", accepted=False
                )
                response = AgenticRAGResponse(
                    query=request.query,
                    answer=state.get("answer", self._settings.no_context_answer),
                    sources=state.get("sources", []),
                    chunks_used=len(state.get("sources", [])),
                    search_mode=state.get("search_mode", "bm25"),
                    model=model,
                    usage=state.get("usage", OllamaUsage()),
                    trace_id=trace.trace_id,
                    reasoning_steps=state.get("reasoning_steps", []),
                    retrieval_attempts=state.get("retrieval_attempts", 0),
                    rewritten_query=state.get("rewritten_query"),
                    guardrail=guardrail,
                    status=state.get("status", "no_context"),
                )
                trace.finish(
                    output={
                        "status": response.status,
                        "retrieval_attempts": response.retrieval_attempts,
                        "chunks_used": response.chunks_used,
                    },
                    metadata={"search_mode": response.search_mode},
                )
                return response
            except BaseException as exc:
                trace.mark_error(exc)
                raise
