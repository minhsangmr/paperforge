# Paperforge

Paperforge is a container-first academic-paper ingestion and RAG project rebuilt from a course template with a production-oriented architecture.

## Current milestone: Week 4

The repository currently provides:

- FastAPI liveness/readiness and request tracing.
- PostgreSQL, Alembic, Redis, and OpenSearch 2.19.
- Rate-limited arXiv ingestion and persistent PDF caching.
- Docling parsing with CPU-only PyTorch in an isolated Linux environment.
- Transactional PostgreSQL paper upserts.
- A versioned paper-level BM25 index and `/api/v1/search` API from Week 3.
- Deterministic section-aware chunking with overlap and reference-section exclusion.
- Async Jina retrieval embeddings with batching, retry, dimension validation, and no fake-vector fallback.
- A separate versioned chunk-level OpenSearch k-NN index.
- BM25, vector, and native reciprocal-rank-fusion hybrid retrieval.
- POST `/api/v1/hybrid-search` with `auto`, `bm25`, `vector`, and `hybrid` modes.
- Safe BM25 fallback when external embeddings are not configured.
- Container-only CLI commands and Airflow indexing for both derived indexes.
- Unit and Docker component tests, including a real OpenSearch RRF round trip.

## Development rules

- macOS runs only VS Code, Git, and Docker Desktop.
- Python, uv, tests, FastAPI, Docling, PyTorch, OpenSearch tooling, and Airflow run in Linux containers.
- `.venv` is stored in Docker volumes, never on the macOS host.
- API credentials are stored only in ignored `.env` or an external secret manager.
- OpenSearch indexes are derived state and can be rebuilt from PostgreSQL.
- A search-schema upgrade must never reset PostgreSQL or PDF-cache volumes.

## First Week 4 run

```bash
cp .env.example .env
# Add PAPERFORGE_EMBEDDINGS__API_KEY to .env.
make build
make lock
make sync
make up-week4
make hybrid-stats
make hybrid-query Q="semantic scientific retrieval" MODE=auto
```

Validate chunk-level BM25 without a Jina key:

```bash
make up-week3
make hybrid-index-text
make hybrid-query Q="agentic retrieval" MODE=bm25
```

Start Airflow only when needed:

```bash
make up-airflow
```

Service URLs:

```text
FastAPI docs:              http://localhost:8000/docs
OpenSearch:                http://localhost:9200
OpenSearch Dashboards:     http://localhost:5601
Airflow:                   http://localhost:8080
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

## Attribution

See `NOTICE.md` and `LICENSE` for the upstream course-template attribution and MIT terms.
