# Week 3: paper-level BM25 search

## Goal

Turn the Week 2 PostgreSQL corpus into a usable keyword-search product without introducing Week 4 vector dependencies.

The completed path is:

```text
arXiv → Docling → PostgreSQL → bulk index → OpenSearch BM25 → FastAPI/CLI
```

## Architecture

### Source of truth

PostgreSQL remains the source of truth. OpenSearch stores a rebuildable projection optimized for retrieval.

### Document identity

Each OpenSearch `_id` is the paper's `arxiv_id`. Repeated indexing updates the same document rather than creating duplicates.

### Indexed fields

| Field | Purpose |
|---|---|
| `arxiv_id` | exact identifier lookup |
| `title` | strongest BM25 field |
| `authors` | author-name matching |
| `abstract` | medium-weight semantic keyword context |
| `raw_text` | parsed full-paper keyword retrieval |
| `categories` | exact filter |
| `published_date` | date filter and sorting |
| `pdf_processed` | processed-only filter |
| timestamps | incremental synchronization |

### Query behavior

The relevance query combines:

- exact `arxiv_id` boost;
- exact title phrase boost;
- multi-field BM25 across title, abstract, raw text, and authors;
- low-weight fuzzy fallback only when the query is at least the configured length.

Two-letter technical queries do not use fuzzy expansion, preserving predictable searches for `AI`, `ML`, `NN`, and `CV`.

## Container-only workflow

All Python, uv, indexing, tests, and search commands run inside Linux containers.

```bash
make up-infra
make migrate
make search-init
make search-index
make search-stats
```

To rebuild only derived search state:

```bash
make search-rebuild
```

This deletes and recreates only the configured OpenSearch index. It does not touch PostgreSQL or PDF volumes.

## CLI operations

### Full synchronization

```bash
make search-index
```

Equivalent container command:

```bash
docker compose run --rm --no-deps api \
  uv run paperforge search-index --refresh --fail-on-errors
```

### Explicit rebuild

```bash
make search-rebuild
```

### Incremental synchronization

```bash
docker compose run --rm --no-deps api \
  uv run paperforge search-index \
  --updated-since 2026-07-24T00:00:00+00:00 \
  --refresh \
  --fail-on-errors
```

### Query from CLI

```bash
make search-query Q="AI agents"
```

Additional example:

```bash
docker compose run --rm --no-deps api \
  uv run paperforge search "transformer retrieval" \
  --category cs.AI \
  --published-from 2025-01-01 \
  --sort published_desc
```

## API operations

### GET

```bash
curl --get http://localhost:8000/api/v1/search \
  --data-urlencode 'q=AI agents' \
  --data-urlencode 'category=cs.AI' \
  --data-urlencode 'page=1' \
  --data-urlencode 'page_size=10'
```

### POST

```bash
curl --request POST http://localhost:8000/api/v1/search \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "transformer retrieval",
    "categories": ["cs.AI", "cs.LG"],
    "published_from": "2025-01-01",
    "processed_only": true,
    "page": 1,
    "page_size": 10,
    "sort": "relevance"
  }'
```

## Airflow flow

The Week 3 DAG sequence is:

```text
ingest_previous_interval
        ↓
index_search_documents
        ↓
report_pipeline_stats
        ↓
cleanup_old_pdf_cache
```

The indexing task uses `updated_at` to avoid a mandatory full backfill on each scheduled run.

## Testing strategy

### Unit tests

- search request validation;
- two-letter query behavior;
- fuzzy fallback threshold;
- filters and pagination;
- versioned index bootstrap;
- bulk response handling;
- result normalization;
- search service limits;
- paper projection;
- GET/POST API behavior.

### Component tests

A real-service test creates one PostgreSQL paper, synchronizes it to a unique temporary OpenSearch index, performs a BM25 query, and cleans up both records.

```bash
make test-component
```

### Manual relevance checks

Run these after indexing:

```bash
make search-query Q="AI"
make search-query Q="ML"
make search-query Q="transformer"
make search-query Q="transformr"
```

The typo query should use the low-weight fuzzy fallback. The two-letter queries should not.

## Acceptance criteria

- the BM25 index mapping contains `_meta.paperforge_schema_version = 1`;
- index document count matches the expected PostgreSQL synchronization scope;
- repeated indexing does not create duplicate papers;
- `AI`, `ML`, `NN`, and `CV` execute successfully;
- exact arXiv ID lookup ranks the matching record first;
- title matches rank above abstract-only and full-text-only matches;
- category/date filters work;
- highlights are returned;
- GET and POST endpoints return the same query model;
- an unavailable/disabled OpenSearch dependency returns HTTP 503;
- the Airflow DAG has no import errors and includes the indexing task;
- unit quality gates and component tests pass;
- PostgreSQL and PDF volumes remain intact.
