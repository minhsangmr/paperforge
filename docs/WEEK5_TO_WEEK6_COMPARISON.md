# Week 5 to Week 6 comparison

## State of the uploaded Week 5 project

The uploaded repository already had a Redis adapter and Redis Compose service, but Redis was used only for health checks and primitive key/value tests. RAG requests always executed retrieval and Ollama generation. The response did not expose cache metadata or a trace ID, and there was no Langfuse SDK, feedback endpoint, or self-hosted observability stack.

## Exact Week 6 scope found in the original project

The original Week 6 notebook and source add two production concerns:

1. Parameter-aware exact-match caching of successful RAG responses in Redis, with a 24-hour default TTL.
2. End-to-end Langfuse instrumentation around the RAG pipeline, plus performance/health inspection.

The final original repository also contains user feedback support associated with Langfuse traces. This upgrade includes feedback because it is part of the observability loop, but does not include any LangGraph/agentic behavior.

## Files mapped from the original architecture

| Original project | Paperforge Week 6 |
|---|---|
| `services/cache/client.py` | `services/cache/rag.py` |
| `services/cache/factory.py` | FastAPI dependency `get_rag_cache` |
| `services/langfuse/client.py` | `services/observability/langfuse.py` |
| `services/langfuse/tracer.py` | `TraceSession` and nested observations |
| cache logic in `routers/ask.py` | `RAGService.answer()` and `RAGService.stream()` |
| feedback in final agentic router | `/api/v1/feedback` |
| Langfuse services in one large Compose file | isolated `compose.langfuse.yaml` |

## Improvements over the original implementation

- redis-py is synchronous, so cache calls are moved to worker threads instead of blocking FastAPI's event loop.
- Cache keys include normalized query, resolved model, top-k, retrieval mode, sorted categories, and a response-schema version.
- Only fully completed answers are cached; interrupted/error streams never write partial content.
- Cache failures degrade to a normal cache miss and do not take RAG offline.
- Cached SSE responses preserve the Week 5 event contract and replay deterministic chunks.
- The response explicitly exposes `cache_hit` and `trace_id`.
- Langfuse uses the current v4 SDK boundary rather than legacy trace/generation APIs.
- Raw prompt/query/answer capture is disabled by default; hashes and lengths are traced instead.
- Application Redis is not shared with Langfuse's internal queue/cache Redis.
- Langfuse is isolated in a second Compose file so the heavy stack is opt-in on an Intel Mac.
- Readiness distinguishes optional Langfuse failure from required core dependencies.

## Deliberately excluded from Week 6

- semantic similarity caching;
- distributed cache invalidation;
- LangGraph document grading or query rewriting;
- agentic retries and graph state;
- Telegram bot integration.

Those are either future hardening tasks or Week 7 scope.
