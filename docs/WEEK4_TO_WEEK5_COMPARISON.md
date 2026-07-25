# Week 4 to Week 5 Comparison

## Audit basis

This comparison was produced from the uploaded `paperforge-week4-complete.zip` and the original course project. It does not assume that an earlier generated patch or scaffold was applied unchanged.

## State of the uploaded Week 4 project

Week 4 already contains the complete retrieval layer:

- deterministic section-aware chunks;
- Jina passage/query embeddings;
- a chunk-level `knn_vector` index;
- BM25, vector, and OpenSearch RRF hybrid modes;
- `/api/v1/hybrid-search`;
- PostgreSQL-to-OpenSearch synchronization;
- Airflow indexing after ingestion.

The existing `infrastructure/ollama.py` is only a health adapter. There is no generation client, grounded prompt, `/ask`, SSE stream, local model bootstrap, or containerized UI.

## Exact Week 5 scope found in the original project

| Original Week 5 responsibility | Paperforge implementation |
|---|---|
| Ollama service and local model | `compose.yaml`, persistent `paperforge_ollama` volume, model-init service |
| Ollama generation client | `services/ollama/client.py` |
| Grounded RAG prompt | `services/ollama/prompts.py` |
| Retrieval + generation orchestration | `services/rag.py` |
| Complete answer endpoint | `POST /api/v1/ask` |
| Streaming endpoint | `POST /api/v1/stream` using SSE |
| Request/response contracts | `schemas/rag.py` |
| Interactive UI | `gradio_app.py` and Compose profile `app-ui` |
| Local operational commands | Week 5 Make targets |

## Explicitly excluded from Week 5

The final original source mixes later features into its `ask` router. These are intentionally excluded:

- Redis exact-answer caching — Week 6;
- Langfuse traces, spans, feedback, and usage dashboards — Week 6;
- LangGraph document grading, query rewriting, and retries — Week 7;
- Telegram Bot — Week 7.

## Architectural corrections relative to the original

1. Gradio never runs with host macOS Python. It has an isolated Linux `.venv` volume.
2. The API and Gradio do not hard-code `localhost` for container-to-container traffic.
3. Streaming uses `text/event-stream` and named `metadata`, `token`, `done`, and `error` events.
4. Retrieval remains a service dependency instead of duplicating OpenSearch logic inside the router.
5. `use_hybrid=true` maps to Week 4 `auto`, preserving BM25 fallback when a Jina key is absent.
6. Prompt context is bounded and every context block gets a stable `[S1]`-style label.
7. Ollama errors are normalized to domain exceptions and HTTP 503 responses.
8. The model is pulled by an explicit one-shot service into a persistent volume.
9. No database migration or destructive volume reset is required.

## Data flow

```text
RAGRequest
   -> HybridSearchService
   -> chunk hits and source metadata
   -> bounded grounded prompt
   -> Ollama /api/generate
   -> complete JSON response or SSE token stream
```

## Derived versus source-of-truth state

Week 5 adds no new PostgreSQL tables. Ollama model files and OpenSearch indexes are derived/runtime state. Existing paper data, PDF cache, BM25 index, and hybrid index are preserved.
