# Paperforge

Paperforge is a container-first academic-paper ingestion and RAG project rebuilt from a course template with a production-oriented architecture.

## Current milestone: Week 3

The repository currently provides:

- FastAPI liveness/readiness and request tracing.
- PostgreSQL, Alembic, Redis, and OpenSearch.
- Rate-limited arXiv ingestion and persistent PDF caching.
- Docling parsing with CPU-only PyTorch in an isolated Linux environment.
- Transactional PostgreSQL paper upserts.
- A versioned, paper-level OpenSearch BM25 index.
- PostgreSQL-to-OpenSearch bulk synchronization with stable document IDs.
- BM25 search across title, abstract, authors, and parsed full text.
- Category/date filters, highlighting, pagination, exact arXiv-ID boost, and optional fuzzy fallback.
- GET and POST `/api/v1/search` endpoints.
- Container-only search CLI and Airflow indexing task.
- Unit, component, external, and Docling test tiers.

## Development rules

- macOS runs only VS Code, Git, and Docker Desktop.
- Python, uv, tests, FastAPI, Docling, PyTorch, OpenSearch tooling, and Airflow run in Linux containers.
- `.venv` is stored in Docker volumes, never on the macOS host.
- Docling/PyTorch are not installed in the lightweight API environment.
- OpenSearch is derived state and can be rebuilt from PostgreSQL; PostgreSQL volumes must not be reset for a search-schema upgrade.

## First run

```bash
cp .env.example .env
make build
make sync
make up-week3
make search-stats
make search-query Q="AI agents"
```

Ingest and immediately index a small metadata batch:

```bash
make ingest-metadata MAX_RESULTS=3
make search-index
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

## Attribution

See `NOTICE.md` and `LICENSE` for the upstream course-template attribution and MIT terms.
