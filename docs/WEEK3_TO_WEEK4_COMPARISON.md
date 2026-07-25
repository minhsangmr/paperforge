# Paperforge Week 3 to Week 4 Comparison

## Audit inputs

This comparison was produced from the actual `paperforge-week3-complete.zip` repository and the upstream course project. No previous patch history or generated scaffold was assumed.

## Week 3 baseline found in the uploaded repository

The uploaded Week 3 project already provides:

- PostgreSQL paper persistence and Alembic-managed schema.
- arXiv ingestion, PDF caching, and Docling parsing.
- A versioned paper-level BM25 OpenSearch index.
- PostgreSQL-to-OpenSearch bulk synchronization.
- BM25 filters, highlighting, pagination, and GET/POST search APIs.
- Airflow ingestion followed by paper-level BM25 indexing.
- Container-only uv, test, and service workflows.

The repository does not yet contain chunking, embedding generation, a vector mapping, a hybrid query, or a chunk-level retrieval API.

## Exact Week 4 boundary in the upstream project

The upstream Week 4 materials identify these capabilities:

1. Section-aware text chunking with overlap.
2. Retrieval embeddings generated with Jina AI.
3. A chunk-level OpenSearch index containing a `knn_vector` field.
4. BM25-only, vector-only, and hybrid retrieval modes.
5. Reciprocal rank fusion of lexical and semantic rankings.
6. A unified FastAPI hybrid-search endpoint.
7. Indexing integration after document ingestion.

The following upstream files are the main Week 4 references:

- `src/services/indexing/text_chunker.py`
- `src/services/indexing/hybrid_indexer.py`
- `src/services/embeddings/jina_client.py`
- `src/services/opensearch/index_config_hybrid.py`
- `src/services/opensearch/query_builder.py`
- `src/routers/hybrid_search.py`
- `airflow/dags/arxiv_ingestion/indexing.py`
- `notebooks/week4/`

## Explicitly out of scope

These features remain outside Week 4:

- Ollama generation, context assembly, citations, and streaming: Week 5.
- Redis response caching and Langfuse tracing: Week 6.
- LangGraph, query rewriting, grading, Telegram, and Agentic RAG: Week 7.

## Differences between upstream and Paperforge implementation

### 1. Two derived search indexes instead of replacing Week 3

The upstream final-state code mixes paper and chunk indexing concerns. Paperforge preserves:

- `paperforge-papers-bm25-v1`: Week 3 paper-level BM25.
- `paperforge-chunks-hybrid-v1`: Week 4 chunk-level BM25/vector/hybrid.

This avoids deleting a working Week 3 index and makes rollback and benchmarking easier.

### 2. Native OpenSearch RRF pipeline

Paperforge uses the OpenSearch 2.19 score-ranker search pipeline with reciprocal rank fusion. The pipeline is created idempotently and versioned independently from the chunk index.

### 3. Current configurable Jina model

The upstream implementation was built around `jina-embeddings-v3`. Paperforge keeps the same 1024-dimensional retrieval architecture but defaults to `jina-embeddings-v5-text-small`, while retaining environment-driven model and dimension settings.

### 4. No committed or notebook-embedded API key

The upstream notebook contains credential-like material. Paperforge includes only an empty placeholder in `.env.example`. The real key belongs only in ignored `.env` or an external secret store.

### 5. Fail-safe replacement of stale chunks

New chunks are indexed before stale chunks are deleted. If a bulk write partially fails, existing indexed content remains available instead of being deleted first.

### 6. Safe BM25 fallback

`mode=auto` uses hybrid retrieval when the embedding key is configured and falls back to chunk-level BM25 when it is not. Explicit `vector` or `hybrid` mode returns a clear service-unavailable response without a key. No fake vectors are generated.

### 7. Stable deterministic chunk IDs

Chunk IDs derive from the arXiv ID, chunk position, section title, and normalized chunk content. Re-running the same source produces stable IDs and idempotent upserts.

### 8. No destructive database reset

Week 4 adds no PostgreSQL table or column. No Alembic migration and no `docker compose down -v` are required. Both OpenSearch indexes are derived state and may be rebuilt independently.

## File-level upgrade summary

### New application files

- `src/paperforge/api/routes/hybrid_search.py`
- `src/paperforge/infrastructure/hybrid_search.py`
- `src/paperforge/schemas/hybrid_search.py`
- `src/paperforge/services/chunking.py`
- `src/paperforge/services/embeddings/__init__.py`
- `src/paperforge/services/embeddings/jina.py`
- `src/paperforge/services/hybrid_indexing.py`
- `src/paperforge/services/hybrid_query.py`
- `src/paperforge/services/hybrid_search.py`

### Modified application and operations files

- `.env.example`
- `Makefile`
- `README.md`
- `airflow/dags/arxiv_paper_ingestion.py`
- `pyproject.toml`
- `uv.lock`
- `src/paperforge/__init__.py`
- `src/paperforge/api/dependencies.py`
- `src/paperforge/api/router.py`
- `src/paperforge/cli.py`
- `src/paperforge/core/config.py`
- `src/paperforge/exceptions.py`
- `src/paperforge/infrastructure/resources.py`
- `src/paperforge/main.py`
- `src/paperforge/schemas/__init__.py`

### New tests

- `tests/component/test_hybrid_search_end_to_end.py`
- `tests/unit/test_chunking.py`
- `tests/unit/test_hybrid_indexing.py`
- `tests/unit/test_hybrid_opensearch.py`
- `tests/unit/test_hybrid_query.py`
- `tests/unit/test_hybrid_search_api.py`
- `tests/unit/test_hybrid_search_service.py`
- `tests/unit/test_jina_embeddings.py`

### Modified tests

- `tests/unit/test_config.py`
- `tests/unit/test_health_api.py`

## Acceptance definition

Week 4 is complete only when:

- The Week 3 BM25 index still works.
- The chunk index and RRF pipeline can be created without resetting PostgreSQL.
- Processed papers are converted into deterministic overlapping chunks.
- Chunk embeddings have the configured dimensions.
- Repeated hybrid indexing creates no duplicate chunk IDs.
- BM25, vector, hybrid, and auto modes work as specified.
- Auto mode safely falls back to BM25 without a Jina key.
- Airflow indexes both the Week 3 paper index and Week 4 chunk index.
- Unit quality gates and Docker component tests pass.
