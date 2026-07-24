# Paperforge

Paperforge is a container-first academic-paper search and agentic RAG platform.
It is being rebuilt incrementally from an MIT-licensed educational template,
with Linux containers as the only Python execution environment.

## Week 0 status

- Dockerized Python 3.12 and uv development environment
- VS Code Dev Container configuration
- FastAPI liveness endpoint
- Ruff, strict MyPy, Pytest, and coverage gates
- Docker-based GitHub Actions CI
- Optional Compose profiles reserved for PostgreSQL, Redis, and OpenSearch

## Non-negotiable development rule

The macOS host runs only VS Code, Git, Docker Desktop, Make, and shell commands.
Do not run `python`, `uv`, `pytest`, `ruff`, `mypy`, or Uvicorn directly on macOS.

## Start Week 0

```bash
cp .env.example .env
make verify-host
make bootstrap  # creates uv.lock inside Linux on the first run
make up
make check
make health
```

Open API documentation at `http://localhost:8000/docs`.

For the complete setup and first GitHub push, read
[`docs/WEEK0_SETUP.md`](docs/WEEK0_SETUP.md).
