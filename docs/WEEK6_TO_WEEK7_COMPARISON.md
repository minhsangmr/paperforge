# Week 6 → Week 7 comparison

## Audit inputs

This comparison was derived from the uploaded Week 6 repository and the original course project, not from an assumed patch base.

## What Week 6 already contains

- Complete and streaming grounded RAG.
- BM25/vector/RRF retrieval.
- Ollama generation.
- Redis response caching.
- Langfuse traces and feedback.
- Gradio.

## Week 7 code in the original project

The original project places final-week functionality mainly in:

- `src/services/agents/agentic_rag.py`
- `src/services/agents/state.py`
- `src/services/agents/models.py`
- `src/services/agents/prompts.py`
- `src/services/agents/nodes/*`
- `src/services/agents/tools.py`
- `src/routers/agentic_ask.py`
- `src/services/telegram/bot.py`
- `src/services/telegram/factory.py`
- `src/schemas/telegram/*`

The intended workflow is:

1. Classify the query against the academic CS/AI scope.
2. Retrieve paper chunks.
3. Grade retrieved documents for relevance.
4. Rewrite and retry when results are weak.
5. Generate a grounded answer when relevant context exists.
6. Expose the workflow through an Agentic API and Telegram bot.

## What was missing from uploaded Week 6

- LangGraph dependency and graph state.
- Scope guardrail.
- LLM relevance grading.
- Query rewrite loop.
- Hard retrieval-attempt bound.
- Agentic request/response schemas.
- Agentic API route.
- Agentic mode in Gradio.
- Telegram settings, API client, handlers, and process entry point.
- Telegram Compose profile and Make targets.

## Deliberate improvements over the original

### 1. Guaranteed termination

The original graph checks a maximum attempt count inside retrieval logic, but tool-routing and message state make the termination path harder to audit. Paperforge Week 7 uses an explicit conditional graph:

```text
grade_documents
  ├── relevant → generate_answer → END
  ├── attempts remaining → rewrite_query → retrieve
  └── limit reached → no_context → END
```

The request may lower or raise the retry count only within a validated range of 1–5.

### 2. No hidden chain-of-thought exposure

The original response returns “reasoning steps.” Paperforge preserves transparency with operational summaries such as “retrieved three chunks” or “rewrote the query,” but does not expose private model reasoning.

### 3. Request parameters actually propagate

`top_k`, `use_hybrid`, model override, categories, and max attempts are passed through the request, service, graph state, and retrieval call. This avoids the original mismatch where factory defaults could override API parameters.

### 4. Telegram is a separate process

The original starts Telegram polling from FastAPI lifespan. With multiple Uvicorn workers, that can create multiple pollers for one bot token. Paperforge adds a dedicated `telegram` service and never starts polling in API lifecycle.

### 5. Telegram calls the API

The bot does not instantiate OpenSearch, embeddings, Ollama, Redis, or LangGraph itself. It calls `/api/v1/agentic-ask`, keeping one implementation of business logic and one observability path.

### 6. Defensive local-model parsing

Ollama decisions are parsed from strict JSON, with tolerant extraction for fenced responses. Guardrail and document grading include deterministic fallback behavior when a small local model returns malformed JSON.

### 7. Existing Week 3–6 paths remain intact

Week 7 adds a new endpoint and UI mode. It does not replace:

- `/api/v1/search`
- `/api/v1/hybrid-search`
- `/api/v1/ask`
- `/api/v1/stream`
- cache endpoints
- feedback endpoint

## Not added

There is no new PostgreSQL table or Alembic migration. The agent graph is request-scoped orchestration over existing derived indexes and services.
