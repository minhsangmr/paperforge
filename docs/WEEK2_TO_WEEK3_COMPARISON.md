# Paperforge Week 2 → Week 3 comparison

This report was produced by comparing the uploaded `paperforge-week2.zip` directly with the original course repository. It does not assume that an earlier scaffold or patch was applied.

## 1. What the uploaded Week 2 project already contains

The uploaded project has a coherent Week 2 vertical slice:

- typed settings and container-only development;
- PostgreSQL with Alembic-managed `papers` table;
- Redis and OpenSearch health adapters;
- arXiv metadata retrieval and PDF cache;
- lazy Docling parsing in the heavy ingestion image;
- transaction-neutral PostgreSQL upserts;
- ingestion CLI and Airflow 3 DAG;
- unit, component, external, and Docling test tiers.

The Airflow DAG explicitly states that OpenSearch indexing starts in Week 3. This is consistent with the current source: ingestion stops after PostgreSQL persistence.

## 2. Search capabilities present before Week 3

Week 2 has only an OpenSearch infrastructure skeleton:

- `OpenSearchClient.ping()`;
- `OpenSearchClient.ensure_index()`;
- a minimal `BASE_PAPER_INDEX` mapping;
- an idempotent bootstrap command;
- OpenSearch readiness reporting.

The Week 2 index is not a complete search implementation. It has no:

- schema version metadata;
- English analyzer or explicit BM25 similarity;
- parsed full-text field;
- strict mapping;
- PostgreSQL-to-OpenSearch synchronization;
- bulk indexing result handling;
- BM25 query builder;
- search schemas or API routes;
- CLI backfill/rebuild operations;
- Airflow indexing task;
- end-to-end search test.

## 3. What the original Week 3 materials intend

The original `notebooks/week3/README.md` and notebook define Week 3 as a paper-level keyword-search milestone:

1. create an OpenSearch paper index;
2. index PostgreSQL paper records;
3. run BM25 multi-field search;
4. boost title over abstract/content;
5. support category/date filters;
6. highlight matched text;
7. paginate and sort results;
8. expose GET and POST search APIs;
9. integrate indexing into Airflow;
10. verify the complete arXiv → PostgreSQL → OpenSearch → API path.

The notebook specifically tests short technical queries such as `AI`, `ML`, `NN`, and `CV`.

## 4. Why the original final source cannot be copied verbatim

The final course source has accumulated later-week functionality inside files that also contain Week 3 concepts:

- `src/services/opensearch/client.py` is now a unified BM25/vector/hybrid client;
- its BM25 path searches chunks rather than one document per paper;
- `src/services/opensearch/index_config_hybrid.py` contains vector mappings and an RRF pipeline;
- `src/services/indexing/hybrid_indexer.py` chunks text and generates embeddings;
- `airflow/dags/arxiv_ingestion/indexing.py` performs chunking and vector embedding;
- the final API exposes `/hybrid-search`, not the clean Week 3 `/search` boundary described by the notebook.

Those elements belong to Week 4 or later and are intentionally excluded from this upgrade.

## 5. Exact Week 3 boundary used by Paperforge

### Included

- versioned paper-level BM25 index;
- English analyzer and explicit BM25 similarity;
- deterministic PostgreSQL projection;
- stable OpenSearch document ID equal to `arxiv_id`;
- bulk upsert and error accounting;
- full index rebuild from PostgreSQL;
- incremental indexing by `updated_at`;
- title, abstract, authors, and parsed-text search;
- exact arXiv-ID and title-phrase boosts;
- safe fuzzy fallback for longer queries;
- no fuzzy expansion for two-letter queries;
- categories, publication dates, and processed-only filters;
- highlighting, pagination, and sort modes;
- GET and POST FastAPI routes;
- CLI commands for indexing, statistics, and search;
- Airflow indexing task after ingestion;
- unit and real-service component tests.

### Excluded

- text chunking;
- embedding generation;
- Jina AI;
- k-NN/vector fields;
- RRF or hybrid search;
- Ollama generation;
- RAG prompts and citations;
- Gradio;
- Langfuse;
- LangGraph and Telegram.

## 6. Database and migration decision

No PostgreSQL migration is needed for Week 3. The Week 1 migration already includes every field needed to build the paper-level search document, including `raw_text`, `pdf_processed`, `created_at`, and `updated_at`.

OpenSearch is derived state. A search-schema change is handled by a new versioned index name or by explicitly rebuilding only that index. Do not run `docker compose down -v`, `make reset`, or delete the PostgreSQL volume.

## 7. Search-index compatibility decision

The uploaded `.env.example` used:

```text
paperforge-papers-v1
```

That existing index has the Week 1 minimal mapping and no schema metadata. Week 3 defaults to:

```text
paperforge-papers-bm25-v1
```

The client stores `paperforge_schema_version` inside mapping `_meta`. If the configured name points to an old unversioned index, bootstrap fails with an actionable error instead of silently searching an incompatible mapping.

This prevents a common failure mode where code appears updated but OpenSearch keeps using a stale persistent mapping.

## 8. Additional repository hygiene found in the uploaded ZIP

The uploaded archive also contains local artifacts:

- `.env` and `.env.week0.backup`;
- `.DS_Store` files;
- `src/paperforge.egg-info`;
- `.cache/models`;
- cached PDF data.

The ZIP does not contain `.git`, so this audit cannot determine whether those files are Git-tracked. They must not be committed. The complete Week 3 reference source excludes them, while the upgrade overlay never deletes local data automatically.
