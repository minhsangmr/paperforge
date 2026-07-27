# Week 7 — Bounded Agentic RAG and Telegram

## Architecture

```text
FastAPI / Gradio / Telegram
            ↓
       AgenticRAGService
            ↓
         LangGraph
  guardrail → retrieve → grade
       ↓          ↑        ↓
 out_of_scope   rewrite   generate
                         or no_context
            ↓
 HybridSearchService + Ollama + Langfuse
```

## Graph state

The state records:

- original and active queries,
- model and retrieval controls,
- retrieval-attempt count,
- guardrail result,
- candidate and relevant chunks,
- document grades,
- rewritten query,
- final answer, citations, usage, and status,
- concise workflow summaries.

## API

Canonical endpoint:

```http
POST /api/v1/agentic-ask
```

Compatibility alias:

```http
POST /api/v1/ask-agentic
```

Example:

```bash
curl -X POST http://localhost:8000/api/v1/agentic-ask \
  -H 'Content-Type: application/json' \
  -d '{
    "query": "How does reciprocal rank fusion improve retrieval?",
    "top_k": 3,
    "use_hybrid": true,
    "max_retrieval_attempts": 2
  }'
```

The response contains the final answer, sources, guardrail result, retrieval count, rewritten query when used, status, trace ID, and workflow summaries.

## Scope behavior

An out-of-scope question returns a deterministic safe answer without calling retrieval. If the local model cannot emit valid guardrail JSON, a conservative keyword fallback is used.

## Relevance grading and rewrite

Retrieved chunks are sent to Ollama in one bounded grading prompt. If none are selected:

- the graph rewrites the query when attempts remain;
- the graph returns `no_context` when the limit is reached.

A malformed grading response falls back to token-overlap grading and never creates fake embeddings or fake sources.

## Observability

Langfuse receives a root `paperforge-agentic-rag` trace and a child `agentic-workflow` observation. Raw content remains controlled by `PAPERFORGE_LANGFUSE__CAPTURE_CONTENT`.

## Gradio

The Week 7 checkbox selects between:

- standard streaming RAG (`/stream`), and
- bounded Agentic RAG (`/agentic-ask`).

Agentic responses display operational workflow summaries, status, retry count, sources, and trace ID.

## Telegram

Telegram uses long polling in a dedicated Compose service.

Required local settings:

```dotenv
PAPERFORGE_TELEGRAM__ENABLED=true
PAPERFORGE_TELEGRAM__BOT_TOKEN=<real token>
```

Optional allowlist:

```dotenv
PAPERFORGE_TELEGRAM__ALLOWED_USER_IDS=[123456789]
```

Start:

```bash
make sync-bot
make up-bot
make telegram-status
make telegram-logs
```

Commands:

- `/start`
- `/help`
- `/status`
- any normal text message runs Agentic RAG

The bot splits long output below Telegram’s message limit and sends plain text to avoid Markdown escaping failures.

## Failure behavior

- Out-of-scope query: deterministic safe response.
- No relevant chunks after retry bound: deterministic no-context response.
- Jina unavailable with `auto`: existing BM25 fallback remains active.
- Ollama unavailable: API returns 503.
- Langfuse unavailable: graph still runs with no-op tracing.
- Telegram API unavailable: bot returns a temporary-error message.
- Telegram token absent: bot process refuses to start, while API and Gradio remain unaffected.

## Acceptance commands

```bash
make compose-config
make check
make test-component
make up-week7
make readiness
make agentic-ask Q="Explain retrieval augmented generation"
make agentic-ask Q="How do I bake bread?"
```

Optional Telegram:

```bash
make up-bot
make telegram-status
```
