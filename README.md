# Paperforge

Paperforge is a container-first academic-paper ingestion and RAG project rebuilt from a course template with a production-oriented architecture.

## Current milestone: Week 6

The repository now provides:

- FastAPI liveness/readiness, request IDs, PostgreSQL, Alembic, Redis, and OpenSearch.
- Rate-limited arXiv ingestion, persistent PDF caching, and Docling parsing.
- Paper-level BM25 plus chunk-level BM25/vector/RRF hybrid retrieval.
- Local Ollama generation, stable `[S1]` citations, SSE streaming, and Gradio.
- Parameter-aware exact-match RAG response caching in application Redis.
- Configurable cache TTL, safe cache failure fallback, cache counters, and exact invalidation.
- Langfuse v4 tracing for cache, retrieval, prompt, and generation stages.
- Trace IDs in complete and streaming API responses.
- User feedback scores attached to Langfuse traces.
- A separate self-hosted Langfuse Compose stack with its own Postgres, ClickHouse, Redis, and MinIO.
- Content capture disabled by default so prompts and answers are represented by hashes and lengths unless explicitly enabled.

## Development rules

- macOS runs only VS Code, Git, and Docker Desktop.
- Python, uv, tests, FastAPI, Gradio, Docling, PyTorch, Airflow, and service clients run in Linux containers.
- `.venv` is stored in Docker volumes, never on the macOS host.
- Secrets live only in ignored `.env` or an external secret manager.
- PostgreSQL is source-of-truth state; OpenSearch indexes and Redis cache entries are derived state.
- The application Redis and Langfuse Redis are intentionally separate services.
- Week 6 does not add LangGraph query rewriting/grading or Telegram; those remain Week 7.

## First Week 6 run

```bash
cp .env.example .env
make observability-secrets
# Copy generated values into .env, then configure Jina/Ollama values as needed.
make build
make lock
make sync
make sync-ui
make up-week6
make readiness
make observability-health
```

Verify cache behavior:

```bash
make rag-ask Q="What is retrieval-augmented generation?"
make rag-ask Q="What is retrieval-augmented generation?"
make cache-stats
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
- `docs/WEEK5_TO_WEEK6_COMPARISON.md`
- `docs/WEEK6_CACHING_OBSERVABILITY.md`

## Attribution

See `NOTICE.md` and `LICENSE` for the upstream course-template attribution and MIT terms.
