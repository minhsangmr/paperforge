"""Retrieval-augmented generation with Week 6 caching and tracing."""

import json
from collections.abc import AsyncIterator

from paperforge.core.config import LangfuseSettings, RAGCacheSettings, RAGSettings
from paperforge.schemas.cache import CachedRAGPayload
from paperforge.schemas.hybrid_search import HybridSearchRequest, HybridSearchResponse, SearchMode
from paperforge.schemas.rag import OllamaUsage, RAGRequest, RAGResponse, RAGStreamEvent
from paperforge.services.cache.rag import RAGCache
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.observability.langfuse import LangfuseObservability, TraceSession
from paperforge.services.ollama.client import OllamaClient
from paperforge.services.ollama.prompts import RAGPromptBuilder


class RAGService:
    """Retrieve, cache, trace, and generate grounded answers."""

    def __init__(
        self,
        retrieval: HybridSearchService,
        ollama: OllamaClient,
        settings: RAGSettings,
        cache: RAGCache | None = None,
        observability: LangfuseObservability | None = None,
    ) -> None:
        self._retrieval = retrieval
        self._ollama = ollama
        self._settings = settings
        self._cache = cache or RAGCache(None, RAGCacheSettings(enabled=False))
        self._observability = observability or LangfuseObservability(
            LangfuseSettings(enabled=False)
        )
        self._prompt_builder = RAGPromptBuilder(
            max_context_characters=settings.max_context_characters,
            max_answer_words=settings.max_answer_words,
        )

    async def answer(self, request: RAGRequest) -> RAGResponse:
        """Return one complete grounded answer, using exact-match cache when possible."""

        model = request.model or self._settings.default_model
        with self._observability.trace_rag(request, streaming=False) as trace:
            with trace.observe(
                name="rag-cache-lookup",
                input_data={
                    "cache_key_parameters": self._cache.build_key(request, resolved_model=model)
                },
            ) as observation:
                lookup = await self._cache.lookup(request, resolved_model=model)
                observation.update(metadata={"cache_hit": lookup.payload is not None})
            if lookup.payload is not None:
                response = self._response_from_cache(lookup.payload, trace.trace_id)
                trace.finish(
                    output={"cache_hit": True, "chunks_used": response.chunks_used},
                    metadata={"search_mode": response.search_mode},
                )
                return response

            retrieval = await self._traced_retrieve(request, trace)
            bundle = self._prompt_builder.build(request.query, retrieval.hits)
            if not bundle.sources:
                response = self._empty_response(request, retrieval, model, trace.trace_id)
                trace.finish(output={"cache_hit": False, "chunks_used": 0})
                return response

            with trace.observe(
                name="rag-prompt",
                input_data=self._observability.content(request.query, label="query"),
                metadata={"sources": len(bundle.sources)},
            ) as prompt_observation:
                prompt_observation.update(
                    output=self._observability.content(bundle.prompt, label="prompt")
                )

            with trace.observe(
                name="ollama-generation",
                as_type="generation",
                input_data=self._observability.content(bundle.prompt, label="prompt"),
                model=model,
            ) as generation:
                answer, usage = await self._ollama.generate(prompt=bundle.prompt, model=model)
                generation.update(
                    output=self._observability.content(answer, label="answer"),
                    usage_details=self._usage_details(usage),
                )

            response = RAGResponse(
                query=request.query,
                answer=answer,
                sources=bundle.sources,
                chunks_used=len(bundle.sources),
                search_mode=retrieval.search_mode,
                model=model,
                usage=usage,
                cache_hit=False,
                trace_id=trace.trace_id,
            )
            with trace.observe(name="rag-cache-store") as cache_store:
                stored = await self._cache.store(request, response, resolved_model=model)
                cache_store.update(metadata={"stored": stored})
            trace.finish(
                output={"cache_hit": False, "chunks_used": response.chunks_used},
                metadata={"search_mode": response.search_mode, "cached": stored},
            )
            return response

    async def stream(self, request: RAGRequest) -> AsyncIterator[RAGStreamEvent]:
        """Yield metadata, tokens, and a final event without caching partial generations."""

        model = request.model or self._settings.default_model
        with self._observability.trace_rag(request, streaming=True) as trace:
            with trace.observe(name="rag-cache-lookup") as observation:
                lookup = await self._cache.lookup(request, resolved_model=model)
                observation.update(metadata={"cache_hit": lookup.payload is not None})
            if lookup.payload is not None:
                response = self._response_from_cache(lookup.payload, trace.trace_id)
                yield self._metadata_event(response)
                for text in self._cache.stream_chunks(response.answer):
                    yield RAGStreamEvent(event="token", data={"text": text})
                yield RAGStreamEvent(
                    event="done",
                    data={
                        "answer": response.answer,
                        "usage": response.usage.model_dump(mode="json"),
                        "cache_hit": True,
                        "trace_id": trace.trace_id,
                    },
                )
                trace.finish(output={"cache_hit": True, "chunks_used": response.chunks_used})
                return

            retrieval = await self._traced_retrieve(request, trace)
            bundle = self._prompt_builder.build(request.query, retrieval.hits)
            metadata = {
                "query": request.query,
                "sources": [source.model_dump(mode="json") for source in bundle.sources],
                "chunks_used": len(bundle.sources),
                "search_mode": retrieval.search_mode,
                "model": model,
                "cache_hit": False,
                "trace_id": trace.trace_id,
            }
            yield RAGStreamEvent(event="metadata", data=metadata)
            if not bundle.sources:
                answer = self._settings.no_context_answer
                yield RAGStreamEvent(
                    event="done",
                    data={
                        "answer": answer,
                        "usage": OllamaUsage().model_dump(mode="json"),
                        "cache_hit": False,
                        "trace_id": trace.trace_id,
                    },
                )
                trace.finish(output={"cache_hit": False, "chunks_used": 0})
                return

            answer_parts: list[str] = []
            usage = OllamaUsage()
            with trace.observe(
                name="ollama-generation",
                as_type="generation",
                input_data=self._observability.content(bundle.prompt, label="prompt"),
                model=model,
            ) as generation:
                async for item in self._ollama.generate_stream(prompt=bundle.prompt, model=model):
                    text = str(item.get("response", ""))
                    if text:
                        answer_parts.append(text)
                        yield RAGStreamEvent(event="token", data={"text": text})
                    if bool(item.get("done", False)):
                        usage = OllamaClient._usage(item)
                answer = "".join(answer_parts).strip()
                generation.update(
                    output=self._observability.content(answer, label="answer"),
                    usage_details=self._usage_details(usage),
                )

            response = RAGResponse(
                query=request.query,
                answer=answer,
                sources=bundle.sources,
                chunks_used=len(bundle.sources),
                search_mode=retrieval.search_mode,
                model=model,
                usage=usage,
                cache_hit=False,
                trace_id=trace.trace_id,
            )
            stored = await self._cache.store(request, response, resolved_model=model)
            yield RAGStreamEvent(
                event="done",
                data={
                    "answer": answer,
                    "usage": usage.model_dump(mode="json"),
                    "cache_hit": False,
                    "cache_stored": stored,
                    "trace_id": trace.trace_id,
                },
            )
            trace.finish(
                output={"cache_hit": False, "chunks_used": len(bundle.sources)},
                metadata={"cached": stored, "search_mode": retrieval.search_mode},
            )

    async def _traced_retrieve(
        self, request: RAGRequest, trace: TraceSession
    ) -> HybridSearchResponse:
        with trace.observe(
            name="hybrid-retrieval",
            input_data=self._observability.content(request.query, label="query"),
            metadata={"top_k": request.top_k, "use_hybrid": request.use_hybrid},
        ) as observation:
            result = await self._retrieve(request)
            observation.update(
                output={"total": result.total, "returned": len(result.hits)},
                metadata={"search_mode": result.search_mode},
            )
            return result

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
        trace_id: str | None,
    ) -> RAGResponse:
        return RAGResponse(
            query=request.query,
            answer=self._settings.no_context_answer,
            sources=[],
            chunks_used=0,
            search_mode=retrieval.search_mode,
            model=model,
            cache_hit=False,
            trace_id=trace_id,
        )

    @staticmethod
    def _response_from_cache(payload: CachedRAGPayload, trace_id: str | None) -> RAGResponse:
        return RAGResponse(
            **payload.model_dump(),
            cache_hit=True,
            trace_id=trace_id,
        )

    @staticmethod
    def _metadata_event(response: RAGResponse) -> RAGStreamEvent:
        return RAGStreamEvent(
            event="metadata",
            data={
                "query": response.query,
                "sources": [source.model_dump(mode="json") for source in response.sources],
                "chunks_used": response.chunks_used,
                "search_mode": response.search_mode,
                "model": response.model,
                "cache_hit": response.cache_hit,
                "trace_id": response.trace_id,
            },
        )

    @staticmethod
    def _usage_details(usage: OllamaUsage) -> dict[str, int]:
        return {
            "input": usage.prompt_tokens,
            "output": usage.completion_tokens,
            "total": usage.total_tokens,
        }


def encode_sse(event: RAGStreamEvent) -> str:
    """Serialize one typed event using the Server-Sent Events wire format."""

    payload = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event}\ndata: {payload}\n\n"
