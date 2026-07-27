# Paperforge

Paperforge is a container-first academic-paper ingestion and Agentic RAG project rebuilt from a course template with a production-oriented Linux architecture.

## Current milestone: Week 7 / v1.0.0

The repository now provides:

- FastAPI liveness/readiness, request IDs, PostgreSQL, Alembic, Redis, and OpenSearch.
- Rate-limited arXiv ingestion, persistent PDF caching, and Docling parsing.
- Paper-level BM25 plus chunk-level BM25/vector/RRF hybrid retrieval.
- Local Ollama generation, stable `[S1]` citations, SSE streaming, and Gradio.
- Parameter-aware exact-match RAG response caching in application Redis.
- Langfuse tracing and trace-linked user feedback.
- A bounded LangGraph workflow with scope guardrail, retrieval, relevance grading, query rewriting, and guaranteed termination.
- `POST /api/v1/agentic-ask` plus a compatibility alias at `/api/v1/ask-agentic`.
- A dedicated Telegram polling container that calls the Agentic API instead of running inside FastAPI workers.
- Gradio support for both standard streaming RAG and bounded Agentic RAG.

## Week 7 workflow

```text
question
   ↓
guardrail
   ├── out of scope → safe response
   └── accepted
          ↓
       retrieve
          ↓
    grade documents
       ├── relevant → grounded answer
       └── not relevant
              ↓
         rewrite query
              ↓
       bounded retry loop
              ↓
   answer or no-context response
```

The public `reasoning_steps` field contains concise workflow summaries, not private model chain-of-thought.

## Development rules

- macOS runs only VS Code, Git, and Docker Desktop.
- Python, uv, tests, FastAPI, Gradio, Docling, PyTorch, Airflow, LangGraph, and Telegram run in Linux containers.
- `.venv` is stored in Docker volumes, never on the macOS host.
- Secrets live only in ignored `.env` or an external secret manager.
- PostgreSQL is source-of-truth state; OpenSearch indexes and Redis cache entries are derived state.
- Telegram polling runs in exactly one dedicated process and is never started from FastAPI lifespan.

## First Week 7 run

```bash
cp .env.example .env
make observability-secrets
# Copy generated Langfuse values into .env.
# Configure Jina, Ollama, and optionally Telegram credentials.
make build
make lock
make sync
make sync-ui
make sync-bot
make up-week7
make readiness
```

Agentic smoke tests:

```bash
make agentic-ask Q="Explain reciprocal rank fusion"
make agentic-ask Q="How do I bake bread?"
```

Optional Telegram:

```bash
# In .env:
# PAPERFORGE_TELEGRAM__ENABLED=true
# PAPERFORGE_TELEGRAM__BOT_TOKEN=<token from BotFather>
make up-bot
make telegram-status
make telegram-logs
```

Service URLs:

```text
FastAPI docs:              http://localhost:8000/docs
Gradio:                    http://localhost:7861
Langfuse:                  http://localhost:3000
Ollama:                    http://localhost:11434
OpenSearch:                http://localhost:9200
OpenSearch Dashboards:     http://localhost:5601
Airflow:                   http://localhost:8080
```

## Documentation

- `docs/WEEK0_SETUP.md`
- `docs/WEEK1_CORE_INFRASTRUCTURE.md`
- `docs/WEEK2_ARXIV_INGESTION.md`
- `docs/WEEK3_BM25_SEARCH.md`
- `docs/WEEK4_HYBRID_SEARCH.md`
- `docs/WEEK5_COMPLETE_RAG.md`
- `docs/WEEK6_CACHING_OBSERVABILITY.md`
- `docs/WEEK6_TO_WEEK7_COMPARISON.md`
- `docs/WEEK7_AGENTIC_RAG_TELEGRAM.md`

## Attribution

See `NOTICE.md` and `LICENSE` for the upstream course-template attribution and MIT terms.
