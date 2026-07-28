# Paperforge

<p align="center">
  <strong>A container-first Agentic RAG platform for ingesting, searching, and asking questions about academic papers.</strong>
</p>

<p align="center">
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white">
  <img alt="FastAPI" src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white">
  <img alt="Docker Compose" src="https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white">
  <img alt="OpenSearch" src="https://img.shields.io/badge/OpenSearch-2.19-005EB8?logo=opensearch&logoColor=white">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-yellow.svg">
  <img alt="Version" src="https://img.shields.io/badge/version-1.0.0-blue">
</p>

Paperforge is a full academic-paper retrieval and question-answering system built around a Linux-container development model. It ingests papers from arXiv, parses PDFs with Docling, stores canonical records in PostgreSQL, builds lexical and vector indexes in OpenSearch, generates grounded answers with a local Ollama model, caches completed responses in Redis, traces RAG workflows with Langfuse, and exposes both standard and bounded Agentic RAG through FastAPI, Gradio, and Telegram.

The repository is designed so that **Python, uv, PyTorch, Docling, Airflow, OpenSearch, Ollama, LangGraph, Gradio, and Telegram all run inside Linux containers**. The host machine only needs Git, VS Code, Docker, and Docker Compose.

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Design decisions](#design-decisions)
- [Technology stack](#technology-stack)
- [Prerequisites](#prerequisites)
- [Quick start](#quick-start)
- [Run without a Jina API key](#run-without-a-jina-api-key)
- [Common workflows](#common-workflows)
- [API reference](#api-reference)
- [Docker services](#docker-services)
- [Configuration](#configuration)
- [Development and testing](#development-and-testing)
- [Project structure](#project-structure)
- [Persistence](#persistence)
- [Security and privacy](#security-and-privacy)
- [Known limitations](#known-limitations)
- [Documentation](#documentation)
- [Attribution](#attribution)
- [License](#license)

## Features

### Ingestion

- Rate-limited arXiv API client with retries, category filters, and date ranges.
- Persistent PDF cache with atomic writes and basic PDF validation.
- Docling parsing inside a dedicated Linux ingestion image.
- CPU-only PyTorch wheels resolved through an explicit uv package index.
- Structured paper sections, references, parser metadata, and processing status.
- Idempotent PostgreSQL upserts.
- Airflow DAG for scheduled ingestion, indexing, reporting, and PDF-cache cleanup.

### Search and retrieval

- Paper-level BM25 search over titles, abstracts, authors, and parsed text.
- Deterministic section-aware chunking with overlap and stable chunk IDs.
- Jina retrieval embeddings with separate query and passage tasks.
- Chunk-level OpenSearch `knn_vector` index using Lucene HNSW.
- BM25, vector, and Reciprocal Rank Fusion hybrid retrieval.
- Category/date filters, pagination, sorting, and highlighted snippets.
- Safe `auto` fallback to BM25 when query embeddings are unavailable.

### Grounded RAG

- Local generation through Ollama.
- Bounded prompts with stable source labels such as `[S1]` and `[S2]`.
- Complete JSON answers and standards-compliant Server-Sent Events.
- Source metadata, token usage, search mode, cache state, and trace IDs.
- No-context behavior when the indexed papers do not support an answer.

### Caching and observability

- Exact-match Redis caching for successfully completed RAG responses.
- Cache keys include query, model, top-k, retrieval mode, categories, and schema version.
- Cached streaming responses preserve `metadata → token → done` SSE semantics.
- Langfuse observations for cache, retrieval, prompt construction, and generation.
- Trace-linked helpful/not-helpful feedback.
- Raw prompt and answer capture disabled by default.

### Bounded Agentic RAG

- Scope guardrail before retrieval.
- Document relevance grading.
- Query rewriting and retry when context is weak.
- Strict retrieval-attempt limit and guaranteed graph termination.
- `completed`, `out_of_scope`, and `no_context` outcomes.
- Workflow summaries without exposing private model chain-of-thought.
- Agentic mode in FastAPI, Gradio, and Telegram.
## Architecture

Paperforge uses a container-first architecture that separates ingestion, storage, retrieval, generation, observability, APIs, and client applications.

<p align="center">
  <a href="docs/images/paperforge-architecture.png">
    <img
      src="docs/images/paperforge-architecture.png"
      alt="Paperforge production architecture"
      width="100%"
    />
  </a>
</p>

<p align="center">
  <em>Click the diagram to open the full-resolution version.</em>
</p>

### Data flow

```text
arXiv metadata and PDFs
        ↓
Docling parsing
        ↓
PostgreSQL — canonical source of truth
        ├── paper projection → BM25 index
        └── section-aware chunks → Jina → vector index
                                      ↓
                              BM25 / vector / RRF
                                      ↓
                       Ollama grounded generation
                                      ↓
                         Redis cache + Langfuse
```

## Design decisions

| Decision | Why |
|---|---|
| Linux containers are the development environment | Prevents host-specific Python, PyTorch, and Docling compatibility issues. |
| PostgreSQL is canonical | OpenSearch indexes and Redis cache can be rebuilt safely. |
| Paper and chunk indexes are separate | Preserves metadata/full-text search while allowing independent vector-index rebuilds. |
| Index schemas are versioned | Prevents silently using incompatible OpenSearch mappings. |
| No fake embeddings | `auto` can fall back to BM25; explicit vector/hybrid requests fail clearly. |
| Agentic retries are bounded | Prevents infinite rewrite/retrieval loops. |
| Telegram is a dedicated process | Avoids duplicate pollers when API worker counts change. |
| Langfuse infrastructure is isolated | Observability data does not share application Redis or PostgreSQL. |
| Completed responses only are cached | Failed or partial generations never become reusable entries. |
| Content tracing is opt-in | Reduces accidental prompt and answer exposure. |

## Technology stack

| Layer | Technology |
|---|---|
| API | FastAPI, Uvicorn, Pydantic v2 |
| Runtime and packages | Python 3.12, uv |
| Containers | Docker, Docker Compose, multi-stage Dockerfile |
| Persistence | PostgreSQL 16, SQLAlchemy 2, Alembic |
| Search | OpenSearch 2.19, BM25, Lucene HNSW, RRF |
| Cache | Redis 7 |
| Ingestion | arXiv, Docling, CPU-only PyTorch |
| Embeddings | Jina Embeddings API |
| Generation | Ollama, default `llama3.2:1b` |
| Agent workflow | LangGraph |
| Scheduling | Apache Airflow 3 |
| Observability | Langfuse v3, ClickHouse, MinIO, isolated Redis/PostgreSQL |
| Interfaces | Swagger UI, Gradio, Telegram |
| Quality | Ruff, strict MyPy, Pytest, coverage, GitHub Actions |

## Prerequisites

Required on the host:

- Git
- Docker Desktop or Docker Engine
- Docker Compose v2
- VS Code with Dev Containers, recommended

The complete stack is resource-intensive. OpenSearch, Ollama, Airflow, ClickHouse, MinIO, PostgreSQL, Redis, Langfuse, Gradio, and the API can be started independently through Compose profiles.

Verify host tools without installing Python:

```bash
make verify-host
```

## Quick start

### 1. Clone and configure

```bash
git clone https://github.com/<your-github-username>/paperforge.git
cd paperforge
cp .env.example .env
```

Build the API image and generate secure local Langfuse values inside Linux:

```bash
make build
make observability-secrets
```

Copy the generated values into `.env` and replace every `CHANGE_ME` placeholder.

For full vector and hybrid retrieval, configure:

```dotenv
PAPERFORGE_EMBEDDINGS__API_KEY=<your-jina-api-key>
```

Telegram is optional and disabled by default.

### 2. Lock and synchronize inside Linux

```bash
make lock
make sync
make sync-ingestion
make sync-ui
make sync-bot
```

No Python or uv command needs to run on the host.

### 3. Validate the repository

```bash
make container-info
make compose-config
make check
```

### 4. Start the main application stack

`make up-week7` builds the vector index and therefore expects a valid Jina API key:

```bash
make up-week7
make ps
make readiness
make observability-health
make ollama-models
```

Airflow and OpenSearch Dashboards are optional and started separately.

### 5. Ingest and index papers

A fresh database has no papers. Add at least one:

```bash
make ingest MAX_RESULTS=1
make search-index
make hybrid-index
```

The first Docling and Ollama runs may download model artifacts into persistent volumes.

### 6. Ask questions

```bash
make rag-ask Q="What is retrieval-augmented generation?"
```

```bash
make agentic-ask \
  Q="How does reciprocal rank fusion improve retrieval?" \
  TOP_K=3 \
  ATTEMPTS=2
```

Open:

- FastAPI docs: <http://localhost:8000/docs>
- Gradio: <http://localhost:7861>
- Langfuse: <http://localhost:3000>

## Run without a Jina API key

Paper-level and chunk-level BM25 work without external embeddings. Do not use `make up-week7`, because its Week 4 setup performs vector indexing.

```bash
make up-infra
make infra-init
make build-ingestion
make sync-ingestion
make up-llm
make ollama-pull
make up-observability
docker compose up --build -d api
make up-ui
```

Then ingest and create text-only indexes:

```bash
make ingest MAX_RESULTS=1
make search-index
make hybrid-index-text
```

Use `auto` or `bm25` retrieval:

```bash
make hybrid-query Q="scientific document retrieval" MODE=auto
make rag-ask Q="What is retrieval-augmented generation?"
```

`auto` resolves to BM25 when query embeddings are unavailable. Explicit vector/hybrid requests return a clear error until a Jina key is configured and embeddings are indexed.

## Common workflows

### Ingestion

```bash
make ingest-metadata MAX_RESULTS=5             # Metadata only
make ingest MAX_RESULTS=3                      # Download and parse PDFs
make ingest-date DATE=2026-07-23 MAX_RESULTS=3
make stats
```

### Search indexing

```bash
make search-index       # PostgreSQL → paper BM25 index
make search-rebuild     # Recreate only the paper index
make search-stats

make hybrid-index       # Chunk and embed processed papers
make hybrid-index-text  # Chunk BM25 without Jina
make hybrid-rebuild     # Recreate only the chunk index and RRF pipeline
make hybrid-stats
```

### Search

```bash
make search-query Q="AI agents"
make hybrid-query Q="semantic document retrieval" MODE=auto
make hybrid-query Q="semantic document retrieval" MODE=hybrid
```

### RAG

```bash
make rag-ask Q="What is RAG?" TOP_K=3 HYBRID=true
make rag-stream Q="Explain attention mechanisms" TOP_K=2
make agentic-ask Q="What are dense retrieval models?" ATTEMPTS=2
```

### Cache and feedback

```bash
make cache-stats
make cache-invalidate Q="What is RAG?" TOP_K=3 HYBRID=true
make feedback TRACE_ID=<trace-id> VALUE=1 COMMENT="Grounded and useful"
```

### Airflow

```bash
make build-airflow
make up-airflow
make airflow-errors
make airflow-dags
```

Airflow UI: <http://localhost:8080>

DAG flow:

```text
ingest_previous_interval
    → index_search_documents
    → index_hybrid_chunks
    → report_pipeline_stats
    → cleanup_old_pdf_cache
```

### Telegram

Configure `.env`:

```dotenv
PAPERFORGE_TELEGRAM__ENABLED=true
PAPERFORGE_TELEGRAM__BOT_TOKEN=<your-bot-token>
PAPERFORGE_TELEGRAM__ALLOWED_USER_IDS=[]
```

Start the dedicated polling process:

```bash
make up-bot
make telegram-status
make telegram-logs
```

The bot supports `/start`, `/help`, `/status`, and normal questions forwarded to the Agentic RAG API.

## API reference

All endpoints use `/api/v1`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/health/live` | API process liveness. |
| `GET` | `/health/ready` | Required and optional dependency readiness. |
| `GET` | `/search` | Bookmarkable paper-level BM25 search. |
| `POST` | `/search` | Advanced paper-level BM25 search. |
| `POST` | `/hybrid-search` | Chunk BM25, vector, or RRF hybrid retrieval. |
| `POST` | `/ask` | Complete grounded RAG answer. |
| `POST` | `/stream` | Grounded RAG answer as SSE. |
| `POST` | `/agentic-ask` | Bounded guardrail, grading, rewriting, and generation workflow. |
| `GET` | `/cache/stats` | RAG cache counters and hit rate. |
| `POST` | `/cache/invalidate` | Delete one exact request cache entry. |
| `POST` | `/feedback` | Attach user feedback to a Langfuse trace. |

`/ask-agentic` is available as a compatibility alias but is hidden from OpenAPI.

### Example: hybrid search

```bash
curl --request POST http://localhost:8000/api/v1/hybrid-search \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "retrieval augmented generation for scientific papers",
    "mode": "auto",
    "categories": ["cs.AI", "cs.IR"],
    "page": 1,
    "page_size": 10
  }'
```

### Example: complete RAG

```bash
curl --request POST http://localhost:8000/api/v1/ask \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "What is retrieval-augmented generation?",
    "top_k": 3,
    "use_hybrid": true
  }'
```

### Example: streaming RAG

```bash
curl --no-buffer --request POST http://localhost:8000/api/v1/stream \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "Explain attention mechanisms",
    "top_k": 2,
    "use_hybrid": true
  }'
```

SSE order:

```text
event: metadata
event: token
...
event: done
```

### Example: Agentic RAG

```bash
curl --request POST http://localhost:8000/api/v1/agentic-ask \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "What are dense retrieval models?",
    "top_k": 3,
    "use_hybrid": true,
    "max_retrieval_attempts": 2
  }'
```

The response includes status, guardrail result, retrieval attempts, optional rewritten query, grounded sources, workflow summaries, usage, and trace ID. `reasoning_steps` contains operational summaries, not hidden chain-of-thought.

## Docker services

| Service | Profile | Port | Purpose |
|---|---|---:|---|
| `workspace` | default | — | VS Code Dev Container. |
| `api` | default | `8000` | FastAPI application. |
| `postgres` | `core` | `5432` | Canonical paper data. |
| `redis` | `core` | `6379` | Application RAG cache. |
| `opensearch` | `search` | `9200` | Paper and chunk indexes. |
| `opensearch-dashboards` | `search-ui` | `5601` | Optional search UI. |
| `ingestion` | `ingestion` | — | Docling and CPU PyTorch. |
| `airflow` | `ingestion` | `8080` | Scheduled pipeline. |
| `ollama` | `llm` | `11434` | Local model server. |
| `gradio` | `app-ui` | `7861` | Browser UI. |
| `telegram` | `bot` | — | Dedicated polling process. |
| `langfuse-web` | `observability` | `3000` | Trace and feedback UI. |
| `langfuse-worker` | `observability` | localhost `3030` | Background worker. |
| `langfuse-clickhouse` | `observability` | localhost only | Analytical storage. |
| `langfuse-minio` | `observability` | `9090` | Object storage. |
| `langfuse-postgres` | `observability` | localhost `5433` | Langfuse relational data. |
| `langfuse-redis` | `observability` | localhost `6380` | Langfuse internal queue/cache. |

Useful commands:

```bash
make up-infra
make up-search-ui
make up-llm
make up-ui
make up-airflow
make up-observability
make up-bot
make up-week7
make ps
make down      # Keep volumes
make reset     # Destructive: delete all Paperforge volumes
```

`make up-week7` starts the main application stack and optional Telegram when enabled. Airflow and OpenSearch Dashboards remain separate.

## Configuration

Typed settings are loaded from environment variables. Nested values use double underscores:

```dotenv
PAPERFORGE_DATABASE__URL=postgresql+psycopg://paperforge:password@postgres:5432/paperforge
PAPERFORGE_OPENSEARCH__URL=http://opensearch:9200
PAPERFORGE_OLLAMA__DEFAULT_MODEL=llama3.2:1b
```

Important groups:

| Area | Examples |
|---|---|
| Database | URL, pool sizes, timeouts |
| arXiv | category, result count, rate limit, PDF cache |
| Docling | page/file limits, OCR, table extraction |
| OpenSearch | index names, schema versions, bulk/page limits |
| Chunking | chunk size, overlap, minimum size, exclusions |
| Jina | API key, model, dimensions, batch and retries |
| Hybrid search | RRF pipeline, HNSW values, candidate limits |
| Ollama | model, temperature, token limit, timeout |
| Cache | namespace, TTL, response schema version |
| Langfuse | credentials, sampling, content capture |
| Agentic RAG | guardrail threshold and retry limits |
| Telegram | token, allowlist, API URL, message limits |

Never commit `.env`. Treat `.env.example` as the configuration contract.

## Development and testing

### Dev Container

Open the repository in VS Code and run:

```text
Dev Containers: Reopen in Container
```

The interpreter is:

```text
/workspace/.venv/bin/python
```

The virtual environment lives in a Docker volume, not on the host filesystem.

### Common developer commands

```bash
make help
make shell
make ingestion-shell
make lock
make sync
make sync-ingestion
make sync-ui
make sync-bot
make logs
make ps
```

### Migrations

```bash
make migrate
make migration MSG="describe the schema change"
```

Application startup does not call `Base.metadata.create_all()`. Alembic owns schema evolution.

### Quality gates

```bash
make format
make check
make test-component
```

Optional integration tests:

```bash
make test-external  # Real arXiv API
make test-docling   # Real one-paper Docling run
```

The repository enforces:

- Ruff formatting and linting
- strict MyPy
- Pytest unit tests
- Docker-backed component tests
- branch coverage
- a 90% minimum coverage gate
- GitHub Actions quality and component jobs

Build the immutable non-root runtime image:

```bash
make build-runtime
```

## Project structure

```text
paperforge/
├── .devcontainer/                 # VS Code Linux workspace
├── .github/                       # CI, Dependabot, PR template
├── airflow/
│   ├── dags/                      # Ingestion and indexing DAG
│   └── Dockerfile                 # Isolated uv-managed Airflow image
├── docs/                          # Architecture notes and runbooks
├── migrations/                    # Alembic revisions
├── scripts/                       # Verification and secret generation
├── src/paperforge/
│   ├── api/                       # FastAPI routes and dependencies
│   ├── core/                      # Settings, logging, request context
│   ├── infrastructure/            # Database, Redis, OpenSearch, Ollama lifecycle
│   ├── middleware/                # Request ID propagation
│   ├── models/                    # SQLAlchemy models
│   ├── repositories/              # Persistence access
│   ├── schemas/                   # Pydantic contracts
│   ├── services/
│   │   ├── agentic/               # Bounded LangGraph workflow
│   │   ├── arxiv/                 # arXiv client and PDF cache
│   │   ├── cache/                 # Redis response cache
│   │   ├── documents/             # Docling adapter
│   │   ├── embeddings/            # Jina adapter
│   │   ├── observability/         # Langfuse adapter
│   │   ├── ollama/                # Generation client and prompts
│   │   └── telegram/              # API client and bot
│   ├── cli.py
│   ├── gradio_app.py
│   ├── main.py
│   └── telegram_app.py
├── tests/
│   ├── unit/
│   ├── component/
│   └── external/
├── compose.yaml
├── compose.langfuse.yaml
├── Dockerfile
├── Makefile
└── pyproject.toml
```

## Persistence

Named volumes preserve state across container recreation:

| Volume | Data |
|---|---|
| `paperforge_postgres` | Paper metadata and parsed content |
| `paperforge_pdf_cache` | arXiv PDFs |
| `paperforge_model_cache` | Docling, Torch, and model artifacts |
| `paperforge_opensearch` | Search indexes |
| `paperforge_redis` | RAG cache and counters |
| `paperforge_ollama` | Ollama models |
| `paperforge_airflow_logs` | Airflow logs |
| `paperforge_*_venv` | Service-specific Linux environments |

PostgreSQL is canonical. BM25 indexes, vector indexes, the RRF pipeline, and Redis answers are derived state and can be rebuilt.

Avoid `make reset` unless deleting all local state is intentional.

## Security and privacy

- Store real credentials only in ignored `.env` files or a secret manager.
- Langfuse content capture defaults to `false`.
- Telegram supports an optional numeric user allowlist.
- The API propagates `X-Request-ID` for correlation.
- Structured JSON logging is configurable.
- The production image runs as a non-root user.
- Telegram polling is isolated from FastAPI workers.
- Optional Redis and Langfuse failures degrade without stopping core behavior where possible.

> [!WARNING]
> The local OpenSearch security plugin is disabled and local ports are published for development convenience. Do not expose this Compose configuration directly to an untrusted network or deploy it unchanged to production.

## Known limitations

- The Compose topology is designed for local development, portfolio demonstrations, and single-host evaluation—not high availability.
- Real vector indexing and vector queries require the external Jina API.
- Ollama CPU latency and answer quality depend on host hardware and model choice.
- The default `llama3.2:1b` model prioritizes local resource usage over maximum answer quality.
- Langfuse self-hosting adds several resource-heavy services.
- Airflow runs in local standalone mode.
- Telegram uses long polling rather than webhooks.
- arXiv availability, PDF quality, and model downloads can affect ingestion.
- Generated answers are not academically authoritative; linked sources should be reviewed.

## Documentation

Detailed phase guides are available in [`docs/`](docs/):

- [`WEEK0_SETUP.md`](docs/WEEK0_SETUP.md)
- [`WEEK1_CORE_INFRASTRUCTURE.md`](docs/WEEK1_CORE_INFRASTRUCTURE.md)
- [`WEEK2_ARXIV_INGESTION.md`](docs/WEEK2_ARXIV_INGESTION.md)
- [`WEEK3_BM25_SEARCH.md`](docs/WEEK3_BM25_SEARCH.md)
- [`WEEK4_HYBRID_SEARCH.md`](docs/WEEK4_HYBRID_SEARCH.md)
- [`WEEK5_COMPLETE_RAG.md`](docs/WEEK5_COMPLETE_RAG.md)
- [`WEEK6_CACHING_OBSERVABILITY.md`](docs/WEEK6_CACHING_OBSERVABILITY.md)
- [`WEEK7_AGENTIC_RAG_TELEGRAM.md`](docs/WEEK7_AGENTIC_RAG_TELEGRAM.md)

The comparison documents explain the exact scope added between phases.

## Attribution

Paperforge is an independent rebuild inspired by and derived in part from the “Production Agentic RAG” / “The Mother of AI Project” course template by Jam With AI.

The original template was distributed under the MIT License with the notice:

> Copyright (c) 2026 Jam With AI

Paperforge preserves that notice in [`LICENSE`](LICENSE). The rebuild introduces a renamed installable package, container-only development, uv dependency management, migration-managed persistence, versioned search schemas, process isolation, stricter quality gates, bounded agent workflows, and corrected runtime boundaries.

This project should not be represented as wholly original work. See [`NOTICE.md`](NOTICE.md) for the full statement.

## License

Distributed under the MIT License. See [`LICENSE`](LICENSE).
