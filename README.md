# Paperforge

Paperforge is a container-first academic-paper search and agentic RAG platform.
It is rebuilt incrementally from an MIT-licensed educational template, with Linux
containers as the only Python execution environment.

## Current milestone: Week 1

- Dockerized Python 3.12 and uv development environment
- FastAPI liveness and dependency-aware readiness endpoints
- Typed nested Pydantic settings
- PostgreSQL through SQLAlchemy 2 and psycopg 3
- Alembic-managed `papers` schema; no runtime `create_all()`
- Idempotent OpenSearch index bootstrap
- Optional Redis and Ollama health adapters
- JSON structured logging and `X-Request-ID` propagation
- Unit and Compose-backed component tests
- OpenSearch Dashboards behind an opt-in Compose profile

## Container-only rule

The macOS host runs only VS Code, Git, Docker Desktop, Make, curl, and shell
commands. Do not run Python, uv, Alembic, Pytest, Ruff, MyPy, or Uvicorn directly
on macOS.

## Start the Week 1 stack

```bash
cp .env.example .env
make bootstrap
make up-week1
make readiness
make check
make test-component
```

Endpoints:

- API documentation: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/api/v1/health/live>
- Readiness: <http://localhost:8000/api/v1/health/ready>
- OpenSearch: <http://localhost:9200>

Start the optional search UI with `make up-search-ui`, then open
<http://localhost:5601>.

Read [`docs/WEEK1_CORE_INFRASTRUCTURE.md`](docs/WEEK1_CORE_INFRASTRUCTURE.md) for
the implementation, verification, testing, and commit sequence.
