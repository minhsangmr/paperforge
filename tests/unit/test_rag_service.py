"""Tests for RAG orchestration without network services."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

from paperforge.core.config import RAGSettings
from paperforge.schemas.hybrid_search import HybridSearchHit, HybridSearchResponse
from paperforge.schemas.rag import OllamaUsage, RAGRequest, RAGStreamEvent
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.rag import RAGService


def _retrieval_response(*, hits: bool = True) -> HybridSearchResponse:
    values = []
    if hits:
        values.append(
            HybridSearchHit(
                chunk_id="c1",
                chunk_index=0,
                arxiv_id="2607.00001",
                title="Grounded Retrieval",
                authors=["Ada Lovelace"],
                abstract="abstract",
                categories=["cs.IR"],
                published_date=datetime.now(UTC),
                pdf_url="https://arxiv.org/pdf/2607.00001.pdf",
                section_title="Methods",
                chunk_text="Retrieval grounds generation in evidence.",
                score=1.0,
            )
        )
    return HybridSearchResponse(
        query="question",
        requested_mode="auto",
        search_mode="hybrid" if hits else "bm25",
        embeddings_used=hits,
        total=len(values),
        page=1,
        page_size=3,
        took_ms=2,
        hits=values,
    )


def test_answer_uses_retrieval_then_ollama() -> None:
    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=_retrieval_response())
    ollama = MagicMock()
    ollama.generate = AsyncMock(
        return_value=(
            "Evidence-backed answer [S1]",
            OllamaUsage(prompt_tokens=5, completion_tokens=4),
        )
    )
    service = RAGService(
        cast(HybridSearchService, retrieval),
        cast(OllamaClient, ollama),
        RAGSettings(),
    )

    response = asyncio.run(service.answer(RAGRequest(query="What is retrieval?")))

    assert response.answer == "Evidence-backed answer [S1]"
    assert response.search_mode == "hybrid"
    assert response.sources[0].citation == "S1"
    retrieval.search.assert_awaited_once()
    ollama.generate.assert_awaited_once()


def test_answer_skips_ollama_when_no_context() -> None:
    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=_retrieval_response(hits=False))
    ollama = MagicMock()
    ollama.generate = AsyncMock()
    settings = RAGSettings(no_context_answer="No grounded evidence.")
    service = RAGService(
        cast(HybridSearchService, retrieval),
        cast(OllamaClient, ollama),
        settings,
    )

    response = asyncio.run(service.answer(RAGRequest(query="Unknown topic")))

    assert response.answer == "No grounded evidence."
    assert response.chunks_used == 0
    ollama.generate.assert_not_awaited()


def test_stream_emits_metadata_tokens_and_done() -> None:
    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=_retrieval_response())
    ollama = MagicMock()

    async def generate_stream(**_: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"response": "Grounded ", "done": False}
        yield {"response": "answer", "done": True, "eval_count": 2}

    ollama.generate_stream = generate_stream
    service = RAGService(
        cast(HybridSearchService, retrieval),
        cast(OllamaClient, ollama),
        RAGSettings(),
    )

    async def collect() -> list[RAGStreamEvent]:
        return [event async for event in service.stream(RAGRequest(query="Question"))]

    events = asyncio.run(collect())
    assert [event.event for event in events] == ["metadata", "token", "token", "done"]
    assert events[-1].data["answer"] == "Grounded answer"


def test_stream_no_context_finishes_without_ollama() -> None:
    retrieval = MagicMock()
    retrieval.search = AsyncMock(return_value=_retrieval_response(hits=False))
    ollama = MagicMock()
    settings = RAGSettings(no_context_answer="No grounded evidence.")
    service = RAGService(
        cast(HybridSearchService, retrieval),
        cast(OllamaClient, ollama),
        settings,
    )

    async def collect() -> list[RAGStreamEvent]:
        return [event async for event in service.stream(RAGRequest(query="Unknown topic"))]

    events = asyncio.run(collect())
    assert [event.event for event in events] == ["metadata", "done"]
    assert events[-1].data["answer"] == "No grounded evidence."
    ollama.generate_stream.assert_not_called()
