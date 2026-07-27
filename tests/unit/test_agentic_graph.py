from collections.abc import Iterable
from datetime import UTC, datetime

import pytest

from paperforge.core.config import AgenticSettings, LangfuseSettings, RAGSettings
from paperforge.schemas.agentic import AgenticRAGRequest
from paperforge.schemas.hybrid_search import (
    HybridSearchHit,
    HybridSearchRequest,
    HybridSearchResponse,
)
from paperforge.schemas.rag import OllamaUsage
from paperforge.services.agentic.service import AgenticRAGService
from paperforge.services.observability.langfuse import LangfuseObservability


class FakeRetrieval:
    def __init__(self, responses: Iterable[HybridSearchResponse]) -> None:
        self.responses = iter(responses)
        self.requests: list[HybridSearchRequest] = []

    async def search(self, request: HybridSearchRequest) -> HybridSearchResponse:
        self.requests.append(request)
        return next(self.responses)


class FakeOllama:
    def __init__(self, responses: Iterable[str]) -> None:
        self.responses = iter(responses)

    async def generate(self, *, prompt: str, model: str) -> tuple[str, OllamaUsage]:
        del prompt, model
        return next(self.responses), OllamaUsage(prompt_tokens=2, completion_tokens=3)


def hit(
    chunk_id: str = "chunk-1",
    text: str = "Retrieval augmented generation uses context.",
) -> HybridSearchHit:
    return HybridSearchHit(
        chunk_id=chunk_id,
        chunk_index=0,
        arxiv_id="2401.00001",
        title="Retrieval Augmented Generation",
        authors=["A. Researcher"],
        abstract="RAG abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 1, 1, tzinfo=UTC),
        pdf_url="https://arxiv.org/pdf/2401.00001",
        section_title="Introduction",
        chunk_text=text,
        score=1.0,
    )


def search_response(query: str, hits: list[HybridSearchHit]) -> HybridSearchResponse:
    return HybridSearchResponse(
        query=query,
        requested_mode="auto",
        search_mode="hybrid",
        embeddings_used=True,
        total=len(hits),
        page=1,
        page_size=3,
        took_ms=2,
        hits=hits,
    )


def service(retrieval: FakeRetrieval, ollama: FakeOllama) -> AgenticRAGService:
    return AgenticRAGService(
        retrieval,  # type: ignore[arg-type]
        ollama,  # type: ignore[arg-type]
        AgenticSettings(),
        RAGSettings(),
        LangfuseObservability(LangfuseSettings(enabled=False)),
    )


@pytest.mark.asyncio
async def test_agentic_happy_path() -> None:
    retrieval = FakeRetrieval([search_response("What is RAG?", [hit()])])
    ollama = FakeOllama(
        [
            '{"score": 95, "reason": "AI research"}',
            '{"relevant_chunk_ids": ["chunk-1"], "reason": "direct support"}',
            "RAG retrieves evidence before generation [S1].",
        ]
    )
    response = await service(retrieval, ollama).answer(AgenticRAGRequest(query="What is RAG?"))
    assert response.status == "completed"
    assert response.retrieval_attempts == 1
    assert response.sources[0].citation == "S1"
    assert [step.step for step in response.reasoning_steps] == [
        "guardrail",
        "retrieve",
        "grade_documents",
        "generate_answer",
    ]


@pytest.mark.asyncio
async def test_agentic_rewrites_once_then_answers() -> None:
    retrieval = FakeRetrieval(
        [
            search_response("ML stuff", [hit("bad", "Unrelated material")]),
            search_response("machine learning research methods", [hit("good")]),
        ]
    )
    ollama = FakeOllama(
        [
            '{"score": 90, "reason": "ML research"}',
            '{"relevant_chunk_ids": [], "reason": "not relevant"}',
            "machine learning research methods",
            '{"relevant_chunk_ids": ["good"], "reason": "relevant"}',
            "Grounded answer [S1].",
        ]
    )
    response = await service(retrieval, ollama).answer(AgenticRAGRequest(query="ML stuff"))
    assert response.status == "completed"
    assert response.retrieval_attempts == 2
    assert response.rewritten_query == "machine learning research methods"


@pytest.mark.asyncio
async def test_agentic_stops_after_retry_bound() -> None:
    retrieval = FakeRetrieval(
        [
            search_response("obscure query", []),
            search_response("obscure query academic research papers", []),
        ]
    )
    ollama = FakeOllama(
        [
            '{"score": 80, "reason": "research request"}',
            "obscure query academic research papers",
        ]
    )
    response = await service(retrieval, ollama).answer(
        AgenticRAGRequest(query="obscure query", max_retrieval_attempts=2)
    )
    assert response.status == "no_context"
    assert response.retrieval_attempts == 2
    assert response.answer


@pytest.mark.asyncio
async def test_agentic_out_of_scope_skips_retrieval() -> None:
    retrieval = FakeRetrieval([])
    ollama = FakeOllama(['{"score": 5, "reason": "cooking"}'])
    response = await service(retrieval, ollama).answer(
        AgenticRAGRequest(query="How do I bake bread?")
    )
    assert response.status == "out_of_scope"
    assert response.retrieval_attempts == 0
    assert retrieval.requests == []
