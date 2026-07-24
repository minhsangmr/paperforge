# Paperforge Week 1 → Week 2 comparison

This comparison was produced from the uploaded `paperforge-week1-complete.zip` and the original course project ZIP. It does not assume that an earlier patch was applied.

## 1. What the uploaded Week 1 project already contains

The uploaded project already has a stronger infrastructure base than the original course repository had at the same point:

- Package namespace `paperforge` under `src/`.
- Python 3.12 and uv running in Linux containers.
- FastAPI liveness and readiness endpoints.
- Typed nested settings.
- PostgreSQL through SQLAlchemy 2 and psycopg 3.
- Alembic-managed schema.
- Redis and OpenSearch adapters.
- Request ID middleware and structured logging.
- Docker-based unit and component CI jobs.
- A `papers` table that already includes the Week 2 PDF-content columns:
  - `raw_text`
  - `sections`
  - `references`
  - `parser_used`
  - `parser_metadata`
  - `pdf_processed`
  - `pdf_processing_date`

Because those columns are already present in migration `20260724_0001`, Week 2 does **not** need a destructive database reset and does **not** need another migration.

## 2. Exact Week 2 surface in the original project

The original Week 2 notebook and README define the following scope:

| Original Week 2 capability | Original files | Week 1 status | Week 2 action |
|---|---|---:|---|
| arXiv settings | `src/config.py` | Missing | Add nested `ArxivSettings` |
| arXiv Atom client | `src/services/arxiv/client.py` | Missing | Add rate-limited async client |
| Date/category filtering | arXiv client and notebook | Missing | Add `from_date`, `to_date`, category query |
| PDF download and cache | arXiv client | Missing | Add atomic cache with validation |
| PDF schemas | `src/schemas/pdf_parser/models.py` | Missing | Add immutable document schemas |
| Docling parser | `src/services/pdf_parser/*` | Missing | Add lazy, thread-offloaded Docling adapter |
| Paper create/upsert schemas | `src/schemas/arxiv/paper.py` | Missing | Add `PaperUpsert` |
| Paper repository | `src/repositories/paper.py` | Missing | Add transaction-neutral upsert repository |
| Pipeline orchestrator | `src/services/metadata_fetcher.py` | Missing | Add `IngestionService` |
| PostgreSQL storage | model/repository | Model exists, repository missing | Reuse existing table and add repository |
| CLI/manual execution | notebook only | Missing | Add `paperforge ingest` and `paperforge stats` |
| Daily automation | `airflow/*` | Missing | Add Airflow 3 local profile and DAG |
| Unit/integration tests | original Week 2 tests | Missing | Add deterministic tests and opt-in live tests |

## 3. Features explicitly excluded from Week 2

The current original repository contains later-week code in its Airflow DAG. The following items are **not** ported into Week 2:

- OpenSearch paper indexing.
- Hybrid retrieval.
- Text chunking.
- Embeddings.
- Reciprocal-rank fusion.
- Ollama generation.
- Langfuse tracing.
- Redis response caching.
- LangGraph agents.
- Telegram bot.

Those belong to Weeks 3–7. The Week 2 DAG ends after PostgreSQL ingestion, reporting, and PDF-cache cleanup.

## 4. Problems found in the original Week 2 implementation

The Week 2 implementation in this project intentionally keeps the original behavior while correcting these issues:

1. **Sync/async mismatch in PDF parsing**  
   The original `PDFParserService` awaits `DoclingParser.parse_pdf`, while the concrete method is synchronous. The new adapter runs conversion with `asyncio.to_thread()`.

2. **Non-atomic PDF cache writes**  
   The original downloader writes directly to the final `.pdf`. A failed download can leave a corrupted cache file. The new client writes `.pdf.part`, validates the header and size, then renames atomically.

3. **Inconsistent rate limiting**  
   Some original API methods do not use the same request limiter. The new client serializes all arXiv traffic through one lock and enforces at least a three-second interval.

4. **Transaction ownership is mixed**  
   The original repository commits from `create()` and `update()`, while the pipeline commits again. The new repository only flushes; the database session context owns commit/rollback.

5. **Existing parsed content can be erased**  
   A later metadata-only upsert should not remove a previous successful parse. The new repository preserves parsed fields unless a new parse succeeds.

6. **Airflow dependency conflict**  
   The original Airflow requirements force SQLAlchemy below 2.0 while the application uses SQLAlchemy 2. The new Airflow image keeps Airflow and Paperforge in separate Python environments inside the same Linux image.

7. **Later-week indexing leaked into the Week 2 DAG**  
   The new DAG contains only ingestion, database reporting, and cache cleanup.

8. **Destructive schema refresh**  
   The original notebook recommends `docker compose down -v`. The uploaded Paperforge project already has the required columns, so Week 2 keeps all volumes and applies normal Alembic checks.

## 5. Files added for Week 2

```text
src/paperforge/cli.py
src/paperforge/exceptions.py
src/paperforge/repositories/__init__.py
src/paperforge/repositories/paper.py
src/paperforge/schemas/papers.py
src/paperforge/services/arxiv/__init__.py
src/paperforge/services/arxiv/client.py
src/paperforge/services/documents/__init__.py
src/paperforge/services/documents/docling_parser.py
src/paperforge/services/ingestion.py
airflow/Dockerfile
airflow/dags/arxiv_paper_ingestion.py
tests/unit/test_arxiv_client.py
tests/unit/test_docling_parser.py
tests/unit/test_ingestion_service.py
tests/unit/test_paper_repository.py
tests/component/test_paper_repository.py
tests/external/test_arxiv_live.py
```

## 6. Files modified for Week 2

```text
.github/workflows/ci.yml
.env.example
Dockerfile
Makefile
README.md
compose.yaml
pyproject.toml
src/paperforge/__init__.py
src/paperforge/core/config.py
src/paperforge/schemas/__init__.py
```

`uv.lock` must be regenerated inside the Linux API container after copying the Week 2 source.
