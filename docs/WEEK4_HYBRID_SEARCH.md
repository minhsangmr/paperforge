# Week 4: Section-Aware Chunking and Hybrid Search

## Architecture

```text
PostgreSQL processed papers
          |
          v
SectionAwareChunker
  - abstract + Docling sections
  - 600-word target
  - 100-word overlap
  - references excluded
          |
          v
Jina retrieval.passage embeddings
          |
          v
paperforge-chunks-hybrid-v1
  - lexical chunk fields
  - 1024-dimensional knn_vector
  - deterministic chunk IDs
          |
          +-----------------------+
          |                       |
          v                       v
BM25 subquery             k-NN vector subquery
          |                       |
          +-----------+-----------+
                      v
       OpenSearch RRF search pipeline
                      |
                      v
       POST /api/v1/hybrid-search
```

The Week 3 paper-level index remains available at the same time.

## Configuration

Copy `.env.example` values into the ignored `.env`. Add the real Jina key only to `.env`:

```dotenv
PAPERFORGE_EMBEDDINGS__API_KEY=jina_your_real_key
```

Core Week 4 settings:

```dotenv
PAPERFORGE_CHUNKING__CHUNK_SIZE_WORDS=600
PAPERFORGE_CHUNKING__OVERLAP_WORDS=100
PAPERFORGE_CHUNKING__MIN_CHUNK_WORDS=80

PAPERFORGE_EMBEDDINGS__MODEL=jina-embeddings-v5-text-small
PAPERFORGE_EMBEDDINGS__DIMENSIONS=1024
PAPERFORGE_EMBEDDINGS__BATCH_SIZE=32

PAPERFORGE_HYBRID_SEARCH__INDEX_NAME=paperforge-chunks-hybrid-v1
PAPERFORGE_HYBRID_SEARCH__SEARCH_PIPELINE=paperforge-hybrid-rrf-v1
PAPERFORGE_HYBRID_SEARCH__BM25_WEIGHT=0.5
PAPERFORGE_HYBRID_SEARCH__VECTOR_WEIGHT=0.5
PAPERFORGE_HYBRID_SEARCH__RRF_RANK_CONSTANT=60
```

Changing the model or dimensions requires an explicit chunk-index rebuild because an OpenSearch vector dimension is immutable for an existing mapping.

## Build and synchronize

All commands run Python and uv inside Linux containers:

```bash
make build
make lock
make sync
make compose-config
make check
```

No new heavyweight local ML package is installed for embeddings; the API uses the existing async HTTP dependency.

## Start infrastructure without deleting data

```bash
make up-infra
make migrate
make search-init
make up
```

Never run `make reset` for a Week 4 upgrade.

## Indexing workflows

### Full chunk and embedding index

Requires `PAPERFORGE_EMBEDDINGS__API_KEY`:

```bash
make hybrid-index
make hybrid-stats
```

### Rebuild only the Week 4 derived index

```bash
make hybrid-rebuild
```

This deletes and recreates only:

- `paperforge-chunks-hybrid-v1`
- `paperforge-hybrid-rrf-v1`

It does not delete PostgreSQL, PDFs, or the Week 3 BM25 index.

### Text-only fallback index

Useful for validating chunking and BM25 before obtaining an API key:

```bash
make hybrid-index-text
make hybrid-stats
make hybrid-query Q="agentic retrieval" MODE=bm25
```

Text-only documents have no vector. Vector and hybrid modes require embedded documents.

## CLI search modes

```bash
make hybrid-query Q="exact transformer terminology" MODE=bm25
make hybrid-query Q="methods that combine lexical and semantic retrieval" MODE=vector
make hybrid-query Q="hybrid scientific search" MODE=hybrid
make hybrid-query Q="hybrid scientific search" MODE=auto
```

Mode behavior:

| Requested mode | Jina key available | Resolved mode |
|---|---:|---|
| `bm25` | Either | BM25 |
| `vector` | Yes | Vector |
| `vector` | No | Error |
| `hybrid` | Yes | RRF hybrid |
| `hybrid` | No | Error |
| `auto` | Yes | RRF hybrid |
| `auto` | No | BM25 fallback |

## API examples

### Auto mode

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

### Explicit hybrid mode with date filters

```bash
curl --request POST http://localhost:8000/api/v1/hybrid-search \
  --header 'Content-Type: application/json' \
  --data '{
    "query": "semantic document retrieval",
    "mode": "hybrid",
    "published_from": "2025-01-01",
    "published_to": "2026-12-31",
    "page": 1,
    "page_size": 10
  }'
```

The response reports both `requested_mode` and the resolved `search_mode`, plus whether query embeddings were used.

## Idempotency validation

```bash
make hybrid-index
make hybrid-stats
make hybrid-index
make hybrid-stats
```

Expected behavior:

- The unique-paper count remains stable.
- Existing deterministic chunk IDs are updated.
- Chunks no longer produced by the current paper content are deleted only after the replacement bulk write succeeds.

## Airflow

```bash
make build-airflow
make up-airflow
make airflow-errors
make airflow-dags
```

The DAG order is:

```text
ingest_previous_interval
  -> index_search_documents
  -> index_hybrid_chunks
  -> report_pipeline_stats
  -> cleanup_old_pdf_cache
```

Airflow receives the Jina key from the ignored Compose `.env` file. Never place the key in the DAG source.

## Testing

```bash
make format
make check
make test-component
```

The new component test inserts a processed PostgreSQL paper, chunks it, uses deterministic test vectors, writes to a temporary real OpenSearch k-NN index, runs a real RRF hybrid query, and cleans up the temporary index, pipeline, and database row.

The component test deliberately avoids calling Jina so CI does not require an external credential.

## Failure scenarios

### Empty or missing API key

`mode=auto` falls back to BM25. Explicit vector/hybrid requests return HTTP 503 with a configuration message.

### Jina 429 or 5xx

The adapter retries with `Retry-After` support or exponential backoff. It does not create dummy vectors.

### Wrong embedding dimensions

The adapter rejects the response before indexing. Rebuild the chunk index if the configured dimension changed.

### Partial OpenSearch bulk failure

The old chunks are preserved. Stale chunks are removed only after the entire replacement batch for that paper succeeds.

### Existing incompatible chunk index

The schema-version check stops startup/indexing with an explicit rebuild instruction. Use `make hybrid-rebuild`; do not delete the PostgreSQL volume.
