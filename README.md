# Paperforge

Paperforge is a container-first academic-paper ingestion and RAG project rebuilt from a course template with a production-oriented architecture.

## Current milestone: Week 5

The repository currently provides:

- FastAPI liveness/readiness and request tracing.
- PostgreSQL, Alembic, Redis, and OpenSearch 2.19.
- Rate-limited arXiv ingestion, persistent PDF caching, and Docling parsing.
- Paper-level BM25 search plus chunk-level BM25, vector, and RRF hybrid retrieval.
- Local Ollama generation with a persistent model volume.
- Grounded prompt construction with stable `[S1]` citations and bounded context.
- `POST /api/v1/ask` for complete RAG responses.
- `POST /api/v1/stream` for standards-compliant Server-Sent Events.
- A Gradio interface running in its own Linux Compose service.
- Safe BM25 retrieval fallback when Jina embeddings are not configured.
- Unit and Docker component tests; no fake vectors or host-side Python.

## Development rules

- macOS runs only VS Code, Git, and Docker Desktop.
- Python, uv, tests, FastAPI, Ollama clients, Gradio, Docling, PyTorch, OpenSearch tooling, and Airflow run in Linux containers.
- `.venv` is stored in Docker volumes, never on the macOS host.
- API credentials are stored only in ignored `.env` or an external secret manager.
- PostgreSQL is source-of-truth state; OpenSearch indexes can be rebuilt.
- Week 5 does not add Redis answer caching or Langfuse tracing; those remain Week 6.

## First Week 5 run

```bash
cp .env.example .env
# Add PAPERFORGE_EMBEDDINGS__API_KEY when real hybrid retrieval is desired.
make build
make lock
make sync
make sync-ui
make up-week5
make ollama-models
make rag-ask Q="What is retrieval-augmented generation?"
```

Streaming:

```bash
make rag-stream Q="Explain attention mechanisms from the indexed papers"
```

Service URLs:

```text
FastAPI docs:              http://localhost:8000/docs
Gradio:                   http://localhost:7861
Ollama:                   http://localhost:11434
OpenSearch:               http://localhost:9200
OpenSearch Dashboards:    http://localhost:5601
Airflow:                  http://localhost:8080
```

## Documentation

- `docs/WEEK0_SETUP.md`
- `docs/WEEK1_CORE_INFRASTRUCTURE.md`
- `docs/WEEK1_TO_WEEK2_COMPARISON.md`
- `docs/WEEK2_ARXIV_INGESTION.md`
- `docs/WEEK2_TO_WEEK3_COMPARISON.md`
- `docs/WEEK3_BM25_SEARCH.md`
- `docs/WEEK3_TO_WEEK4_COMPARISON.md`
- `docs/WEEK4_HYBRID_SEARCH.md`
- `docs/WEEK4_TO_WEEK5_COMPARISON.md`
- `docs/WEEK5_COMPLETE_RAG.md`

## Attribution

See `NOTICE.md` and `LICENSE` for the upstream course-template attribution and MIT terms.
