# Paperforge

Paperforge is a container-first academic-paper ingestion and RAG project rebuilt from a course template with a production-oriented architecture.

## Current milestone: Week 2

The repository currently provides:

- FastAPI liveness/readiness.
- PostgreSQL, Alembic, Redis, and OpenSearch.
- Structured logging and request IDs.
- A rate-limited arXiv Atom client.
- Persistent and atomically written PDF cache.
- Docling parsing with CPU-only PyTorch in an isolated Linux environment.
- Transactional PostgreSQL paper upserts.
- A container-only ingestion CLI.
- An Airflow 3 daily ingestion DAG.
- Unit, component, external, and Docling test tiers.

## Development rules

- macOS runs only VS Code, Git, and Docker Desktop.
- Python, uv, tests, FastAPI, Docling, PyTorch, and Airflow run in Linux containers.
- `.venv` is stored in Docker volumes, never on the macOS host.
- Docling/PyTorch are not installed in the lightweight API environment.

## First run

```bash
cp .env.example .env
make build
make lock
make sync
make up-week2
make ingest-metadata MAX_RESULTS=2
```

Install the heavy ingestion extra:

```bash
make build-ingestion
make sync-ingestion
make ingest MAX_RESULTS=1
```

Start Airflow only when needed:

```bash
make up-airflow
```

Airflow UI:

```text
http://localhost:8080
```

## Documentation

- `docs/WEEK0_SETUP.md`
- `docs/WEEK1_CORE_INFRASTRUCTURE.md`
- `docs/WEEK1_TO_WEEK2_COMPARISON.md`
- `docs/WEEK2_ARXIV_INGESTION.md`

## Attribution

See `NOTICE.md` and `LICENSE` for the upstream course-template attribution and MIT terms.
