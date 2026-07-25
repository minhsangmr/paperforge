"""Retrieval-augmented generation orchestration."""

import json
from collections.abc import AsyncIterator

from paperforge.core.config import RAGSettings
from paperforge.schemas.hybrid_search import (
    HybridSearchRequest,
    HybridSearchResponse,
    SearchMode,
)
from paperforge.schemas.rag import OllamaUsage, RAGRequest, RAGResponse, RAGStreamEvent
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.ollama.prompts import RAGPromptBuilder


class RAGService:
    """Retrieve chunks, construct a grounded prompt, and call Ollama."""

    def __init__(
        self,
        retrieval: HybridSearchService,
        ollama: OllamaClient,
        settings: RAGSettings,
    ) -> None:
        self._retrieval = retrieval
        self._ollama = ollama
        self._settings = settings
        self._prompt_builder = RAGPromptBuilder(
            max_context_characters=settings.max_context_characters,
            max_answer_words=settings.max_answer_words,
        )

    async def answer(self, request: RAGRequest) -> RAGResponse:
        """Return one complete grounded answer."""

        retrieval = await self._retrieve(request)
        model = request.model or self._settings.default_model
        bundle = self._prompt_builder.build(request.query, retrieval.hits)
        if not bundle.sources:
            return self._empty_response(request, retrieval, model)
        answer, usage = await self._ollama.generate(prompt=bundle.prompt, model=model)
        return RAGResponse(
            query=request.query,
            answer=answer,
            sources=bundle.sources,
            chunks_used=len(bundle.sources),
            search_mode=retrieval.search_mode,
            model=model,
            usage=usage,
        )

    async def stream(self, request: RAGRequest) -> AsyncIterator[RAGStreamEvent]:
        """Yield metadata, tokens, and a final completion event."""

        retrieval = await self._retrieve(request)
        model = request.model or self._settings.default_model
        bundle = self._prompt_builder.build(request.query, retrieval.hits)
        metadata = {
            "query": request.query,
            "sources": [source.model_dump(mode="json") for source in bundle.sources],
            "chunks_used": len(bundle.sources),
            "search_mode": retrieval.search_mode,
            "model": model,
        }
        yield RAGStreamEvent(event="metadata", data=metadata)
        if not bundle.sources:
            answer = self._settings.no_context_answer
            yield RAGStreamEvent(
                event="done",
                data={"answer": answer, "usage": OllamaUsage().model_dump(mode="json")},
            )
            return

        answer_parts: list[str] = []
        usage = OllamaUsage()
        async for item in self._ollama.generate_stream(prompt=bundle.prompt, model=model):
            text = str(item.get("response", ""))
            if text:
                answer_parts.append(text)
                yield RAGStreamEvent(event="token", data={"text": text})
            if bool(item.get("done", False)):
                usage = OllamaClient._usage(item)
        yield RAGStreamEvent(
            event="done",
            data={
                "answer": "".join(answer_parts).strip(),
                "usage": usage.model_dump(mode="json"),
            },
        )

    async def _retrieve(self, request: RAGRequest) -> HybridSearchResponse:
        mode: SearchMode = "auto" if request.use_hybrid else "bm25"
        return await self._retrieval.search(
            HybridSearchRequest(
                query=request.query,
                mode=mode,
                categories=request.categories,
                page=1,
                page_size=min(request.top_k, self._settings.max_top_k),
            )
        )

    def _empty_response(
        self,
        request: RAGRequest,
        retrieval: HybridSearchResponse,
        model: str,
    ) -> RAGResponse:
        return RAGResponse(
            query=request.query,
            answer=self._settings.no_context_answer,
            sources=[],
            chunks_used=0,
            search_mode=retrieval.search_mode,
            model=model,
        )


def encode_sse(event: RAGStreamEvent) -> str:
    """Serialize one typed event using the Server-Sent Events wire format."""

    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {payload}\n\n"
