# Week 2 — arXiv ingestion, Docling, PostgreSQL, and Airflow

## Goal

At the end of Week 2, Paperforge can:

1. Query the arXiv Atom API by category and date.
2. Respect arXiv request pacing.
3. Download PDFs into a persistent Docker volume.
4. Validate and cache downloads atomically.
5. Parse PDFs with Docling and CPU-only PyTorch inside Linux.
6. Upsert metadata and parsed content into PostgreSQL.
7. Continue when one paper fails.
8. Run manually through a CLI.
9. Run on a schedule through an Airflow 3 DAG.

## Important architecture decisions

### Separate lightweight and ingestion environments

The FastAPI service does not install Docling or PyTorch. Compose uses two uv virtual-environment volumes:

- `paperforge_venv` for API, lint, typing, and unit tests.
- `paperforge_ingestion_venv` for Docling and CPU-only PyTorch.

This keeps normal iteration fast while preserving a reproducible Linux-only ingestion environment.

### CPU-only PyTorch

`pyproject.toml` maps `torch` to the explicit PyTorch CPU wheel index. PyPI remains the source for all other dependencies.

### No new database migration

Week 1 already created every Week 2 persistence field. Do not run `docker compose down -v`.

### Airflow isolation

The Airflow image contains:

- Airflow in the official image environment.
- Paperforge in `/opt/paperforge/.venv`, created by uv with the `ingestion` extra.

This avoids merging Airflow's application dependency graph with Paperforge's dependency graph.

## Upgrade without `git apply`

Two artifacts are generated from the uploaded Week 1 repository:

- `paperforge-week2-upgrade.zip`: recommended; contains only 20 new and 11 changed files, plus a preview/copy script.
- `paperforge-week2-complete.zip`: a clean complete source tree for inspection and comparison.

Neither workflow deletes files or applies a Git patch. The overlay does not contain `.env`, `uv.lock`, `.git`, local data, or Docker volumes.

### Recommended: preview and copy the audited overlay

```bash
cd ~/Developer/paperforge
git status
git switch -c week-2/arxiv-ingestion

mkdir -p ~/Developer/paperforge-week2-upgrade-source
unzip ~/Downloads/paperforge-week2-upgrade.zip \
  -d ~/Developer/paperforge-week2-upgrade-source

cd ~/Developer/paperforge-week2-upgrade-source/paperforge-week2-upgrade
./preview-and-copy.sh preview ~/Developer/paperforge
./preview-and-copy.sh copy ~/Developer/paperforge
```

The script uses `rsync` without `--delete`, refuses a dirty Git working tree, and leaves `.env` and the existing Week 1 `uv.lock` untouched. After reviewing `git diff`, regenerate the lockfile in Linux with `make lock`.

### Alternative: compare the complete source tree manually

The complete generated ZIP is derived from the uploaded Week 1 project.

### 1. Confirm the destination branch

```bash
cd ~/Developer/paperforge
git status
git branch --show-current
```

### 2. Extract the generated project outside the repository

```bash
mkdir -p ~/Developer/paperforge-week2-source
unzip ~/Downloads/paperforge-week2-complete.zip -d ~/Developer/paperforge-week2-source
```

The source directory will be:

```text
~/Developer/paperforge-week2-source/paperforge/
```

### 3. Review differences before copying

```bash
diff -ru \
  --exclude=.git \
  --exclude=.env \
  --exclude=.venv \
  --exclude=data \
  --exclude=uv.lock \
  ~/Developer/paperforge \
  ~/Developer/paperforge-week2-source/paperforge \
  | less
```

### 4. Copy source files while preserving local state

```bash
rsync -av \
  --exclude='.git/' \
  --exclude='.env' \
  --exclude='.venv/' \
  --exclude='data/' \
  --exclude='logs/' \
  --exclude='uv.lock' \
  ~/Developer/paperforge-week2-source/paperforge/ \
  ~/Developer/paperforge/
```

This is a normal file copy, not a patch operation.

### 5. Refresh `.env` without replacing secrets

Do not overwrite the existing `.env`. Compare it with the new example:

```bash
cd ~/Developer/paperforge
diff -u .env .env.example || true
```

Append the Week 2 variables from `.env.example`, especially:

```dotenv
AIRFLOW_DB=paperforge_airflow
PAPERFORGE_ARXIV__CATEGORY=cs.AI
PAPERFORGE_ARXIV__RATE_LIMIT_SECONDS=3
PAPERFORGE_ARXIV__PDF_CACHE_DIR=/workspace/data/arxiv_pdfs
PAPERFORGE_DOCUMENT_PARSER__MAX_PAGES=30
PAPERFORGE_DOCUMENT_PARSER__MAX_FILE_SIZE_MB=20
PAPERFORGE_DOCUMENT_PARSER__DO_OCR=false
PAPERFORGE_INGESTION__MAX_CONCURRENT_DOWNLOADS=2
PAPERFORGE_INGESTION__MAX_CONCURRENT_PARSES=1
```

## Dependency setup

The generated source does not ship a newly resolved lockfile because lock resolution must happen in your Linux container. Keep the Week 1 lockfile in place; `make lock` updates it from the changed `pyproject.toml`.

```bash
cd ~/Developer/paperforge
make build
make lock
make sync
make build-ingestion
make sync-ingestion
```

Verify CPU-only PyTorch:

```bash
docker compose --profile ingestion run --rm ingestion \
  uv run python -c "import torch; print(torch.__version__); print(torch.version.cuda)"
```

Expected:

```text
<torch version>
None
```

Verify Docling imports:

```bash
docker compose --profile ingestion run --rm ingestion \
  uv run python -c "import docling; print('docling ok')"
```

## Start Week 2 services

```bash
make up-week2
make ps
make readiness
```

`up-week2` starts the Week 1 stack, runs Alembic, bootstraps OpenSearch, builds the ingestion image, and installs the ingestion extra in its own uv environment.

## Run a metadata-only smoke test first

This validates arXiv → schema → repository → PostgreSQL without loading Docling models:

```bash
make ingest-metadata MAX_RESULTS=2
make stats
```

Expected report fields:

```json
{
  "papers_fetched": 2,
  "pdfs_available": 0,
  "pdfs_parsed": 0,
  "papers_created": 2,
  "papers_updated": 0,
  "issues": [],
  "papers_stored": 2
}
```

Running it again should update rather than duplicate:

```bash
make ingest-metadata MAX_RESULTS=2
make stats
```

The total paper count should remain stable for the same arXiv identifiers.

## Run one real Docling ingestion

```bash
make ingest MAX_RESULTS=1
make stats
```

The first conversion can be slow because Docling downloads model artifacts into `paperforge_model_cache`. Later runs reuse the volume.

Inspect the stored row:

```bash
docker compose exec postgres psql \
  -U paperforge \
  -d paperforge \
  -c "select arxiv_id, pdf_processed, length(raw_text) as chars, parser_used from papers order by created_at desc limit 5;"
```

## Test date filtering

```bash
make ingest-date DATE=2026-07-23 MAX_RESULTS=3
```

The CLI accepts both `YYYY-MM-DD` and `YYYYMMDD`.

## Test PDF cache behavior

Run the same date twice:

```bash
make ingest-date DATE=2026-07-23 MAX_RESULTS=1
make ingest-date DATE=2026-07-23 MAX_RESULTS=1
```

The second report should show a nonzero `pdf_cache_hits` value when the same versioned arXiv ID is returned.

List cache files inside Linux:

```bash
docker compose --profile ingestion run --rm ingestion \
  find /workspace/data/arxiv_pdfs -maxdepth 1 -type f -name '*.pdf' -ls
```

## Start Airflow

```bash
make up-airflow
make airflow-logs
```

Open:

```text
http://localhost:8080
```

The Compose profile enables the Airflow simple auth manager's local all-admin mode. This is for local development only.

Verify the DAG:

```bash
make airflow-dags
make airflow-errors
```

Expected DAG ID:

```text
paperforge_arxiv_ingestion
```

There must be no import errors.

The DAG schedule is:

```text
06:00 UTC, Monday through Friday
```

The tasks are:

```text
ingest_previous_interval
  → report_database_stats
  → cleanup_old_pdf_cache
```

OpenSearch indexing is intentionally absent until Week 3.

## Testing strategy

### Lightweight quality gates

```bash
make format
make check
```

These do not install Docling or PyTorch.

### PostgreSQL/OpenSearch/Redis component tests

```bash
make test-component
```

Week 2 adds a real PostgreSQL idempotent-upsert test.

### Opt-in external arXiv test

```bash
make test-external
```

This makes a real network request and should not be part of every CI run.

### Opt-in Docling end-to-end test

```bash
make test-docling
```

This fetches and parses one real paper. It is intentionally excluded from the lightweight CI job because model downloads and conversion are expensive.

## Acceptance criteria

Week 2 is complete when all of the following are true:

```text
[ ] make lock completes inside Linux
[ ] make sync completes
[ ] make sync-ingestion completes
[ ] torch.version.cuda prints None
[ ] Docling imports in the ingestion container
[ ] make check passes
[ ] make test-component passes
[ ] metadata-only ingestion stores at least one paper
[ ] repeating the same ingestion does not create duplicates
[ ] one-paper Docling ingestion stores raw_text
[ ] PDF cache survives container recreation
[ ] a malformed or failed PDF does not abort the whole batch
[ ] existing parsed content survives a later metadata-only upsert
[ ] Airflow starts on port 8080
[ ] paperforge_arxiv_ingestion is listed
[ ] Airflow reports zero DAG import errors
[ ] GitHub Actions remains green
[ ] working tree is clean after commits
```

## Suggested commits

```text
feat(config): add arxiv and document ingestion settings
feat(arxiv): add rate-limited atom client and atomic pdf cache
feat(documents): add lazy docling parser
feat(db): add transaction-neutral paper upsert repository
feat(ingestion): add resilient arxiv-to-postgres pipeline and cli
build(ingestion): add cpu-only pytorch and isolated docling environment
feat(airflow): schedule daily paper ingestion
 test: add ingestion unit component and external suites
 docs: document week two architecture and operations
```
