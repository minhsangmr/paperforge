# Week 1 — Core API and infrastructure

## Outcome

Week 1 creates a stable platform layer for the later ingestion and RAG phases.
At the end of this week, Paperforge owns typed configuration, lifecycle-managed
clients, migration-managed PostgreSQL schema, OpenSearch bootstrap, optional
Redis behavior, dependency readiness, and request-level structured logs.

No Python command in this guide runs on macOS. `make` and Docker commands run on
the host, but every Python, uv, Alembic, Ruff, MyPy, and Pytest process runs in a
Linux container.

## Architecture decisions

1. **Alembic is the only schema authority.** FastAPI startup never calls
   `Base.metadata.create_all()`.
2. **API startup does not block on external services.** Client objects are built
   without network I/O. Readiness probes perform connectivity checks.
3. **Required and optional dependencies are distinct.** PostgreSQL and
   OpenSearch are required by default. Redis is optional. Ollama is represented
   in readiness but disabled until a later phase.
4. **Readiness semantics are explicit.** Required dependency failure returns
   HTTP 503 and `not_ready`. Optional enabled dependency failure returns HTTP 200
   and `degraded`. An intentionally disabled optional dependency is `disabled`
   and does not degrade the application.
5. **Compose volumes own state.** PostgreSQL, Redis, and OpenSearch data survive
   container recreation. `make reset` is the only standard command that deletes
   the volumes.

## 1. Create the Week 1 branch

From macOS Terminal in the repository:

```bash
git switch main
git pull --ff-only
git status
git switch -c week-1/core-infrastructure
```

The working tree must be clean before applying Week 1 changes.

## 2. Apply the supplied Week 1 files

The complete Week 1 archive is a reference implementation. Copy its contents
onto the existing Week 0 repository without copying any `.git` directory.

After applying the files:

```bash
cp .env.example .env
make compose-config
```

Review the change set before locking dependencies:

```bash
git status --short
git diff --stat
git diff -- pyproject.toml compose.yaml Makefile
```

## 3. Regenerate the uv lock inside Linux

Week 1 adds SQLAlchemy, psycopg, Alembic, OpenSearch, Redis, and runtime HTTP
health dependencies. Regenerate and sync the lock only inside the container:

```bash
make build
make lock
make sync
```

Confirm that the lockfile changed:

```bash
git status --short uv.lock
git diff --stat uv.lock
```

Do not run `uv lock` or `uv sync` in a macOS terminal outside Docker.

## 4. Start persistent infrastructure

```bash
make up-infra
make ps
```

Expected services:

- `postgres` is healthy on port 5432.
- `redis` is healthy on port 6379.
- `opensearch` is healthy on port 9200.

The wait script checks actual service commands rather than relying only on a
container being in the running state.

## 5. Apply the database migration

```bash
make migrate
```

Expected Alembic revision:

```text
20260724_0001 (head)
```

Verify migration state inside Linux:

```bash
docker compose run --rm --no-deps api uv run alembic current
docker compose run --rm --no-deps api uv run alembic heads
```

Verify the table from the PostgreSQL container:

```bash
docker compose exec postgres \
  psql -U paperforge -d paperforge -c '\dt'
```

The output must include `alembic_version` and `papers`.

## 6. Bootstrap OpenSearch idempotently

```bash
make search-init
make search-init
```

The first run should report `created`; the second should report
`already_exists`.

Inspect the index:

```bash
curl --fail --silent \
  http://localhost:9200/paperforge-papers-v1 | \
  docker compose run --rm -T --no-deps api uv run python -m json.tool
```

The Week 1 mapping is intentionally small. Week 3 will introduce the production
BM25 mapping and query behavior.

## 7. Start and verify the API

```bash
make up
make health
make readiness
```

A healthy Week 1 readiness response resembles:

```json
{
  "status": "ready",
  "service": "paperforge-api",
  "version": "0.2.0",
  "environment": "development",
  "checks": {
    "postgresql": {"status": "healthy", "required": true},
    "opensearch": {"status": "healthy", "required": true},
    "redis": {"status": "healthy", "required": false},
    "ollama": {"status": "disabled", "required": false}
  }
}
```

Verify request ID propagation:

```bash
curl -i \
  -H 'X-Request-ID: week1-manual-check' \
  http://localhost:8000/api/v1/health/live
```

The response must include:

```text
X-Request-ID: week1-manual-check
```

Follow structured logs:

```bash
make logs
```

Each API request log should contain JSON fields including `request_id`,
`method`, `path`, `status_code`, and `duration_ms`.

## 8. Verify degraded and unavailable states

### Optional Redis failure

Stop Redis while the API remains running:

```bash
docker compose stop redis
make readiness
```

Expected behavior:

- HTTP status remains 200.
- Overall status is `degraded`.
- Redis is `unhealthy` and `required` is false.
- Liveness remains HTTP 200.

Restore Redis:

```bash
docker compose --profile core up -d redis
make wait-infra
```

### Required OpenSearch failure

```bash
docker compose stop opensearch
curl -i http://localhost:8000/api/v1/health/ready
```

Expected behavior:

- HTTP status is 503.
- Overall status is `not_ready`.
- Liveness still returns HTTP 200.

Restore it:

```bash
docker compose --profile search up -d opensearch
make wait-infra
make search-init
```

## 9. Run quality and component tests

Fast unit/static gate:

```bash
make format
make check
```

Real service tests:

```bash
make test-component
```

The component suite verifies:

- Alembic created the `papers` table.
- PostgreSQL executes a real query.
- Redis performs set/get and returns a positive TTL.
- OpenSearch index bootstrap is idempotent.

## 10. Verify persistence

Create a Redis value:

```bash
docker compose exec redis redis-cli SET paperforge:persistence ok
docker compose exec redis redis-cli SAVE
```

Record database and search state:

```bash
docker compose exec postgres \
  psql -U paperforge -d paperforge -c 'select version_num from alembic_version;'

curl --fail --silent \
  http://localhost:9200/_cat/indices/paperforge-papers-v1?v
```

Recreate containers without deleting volumes:

```bash
make down
make up-week1
```

Verify again:

```bash
docker compose exec redis redis-cli GET paperforge:persistence
docker compose exec postgres \
  psql -U paperforge -d paperforge -c 'select version_num from alembic_version;'

curl --fail --silent \
  http://localhost:9200/_cat/indices/paperforge-papers-v1?v
```

The Redis value, Alembic revision, and OpenSearch index must remain.

## 11. Optional OpenSearch Dashboards

OpenSearch Dashboards is not part of the default Week 1 stack because it consumes
extra memory.

```bash
make up-search-ui
```

Open <http://localhost:5601>. Stop the UI when not needed:

```bash
docker compose stop opensearch-dashboards
```

## 12. Commit sequence

Keep each commit focused. Run the relevant tests before each commit.

### Commit 1 — typed settings

```bash
git add pyproject.toml uv.lock .env.example \
  src/paperforge/core/config.py tests/unit/test_config.py

git commit -m "feat(config): add typed application settings"
```

### Commit 2 — PostgreSQL and Alembic

```bash
git add alembic.ini migrations/ \
  src/paperforge/models/ \
  src/paperforge/infrastructure/database.py \
  tests/unit/test_database.py tests/component/test_postgres.py

git commit -m "feat(db): add postgres persistence and alembic migrations"
```

### Commit 3 — OpenSearch

```bash
git add compose.yaml Makefile scripts/wait-for-infra.sh \
  src/paperforge/infrastructure/opensearch.py \
  src/paperforge/infrastructure/bootstrap.py \
  tests/unit/test_opensearch.py tests/component/test_opensearch.py

git commit -m "feat(search): add opensearch client and index bootstrap"
```

### Commit 4 — Redis and resource lifecycle

```bash
git add src/paperforge/infrastructure/redis.py \
  src/paperforge/infrastructure/ollama.py \
  src/paperforge/infrastructure/resources.py \
  tests/unit/test_redis.py tests/unit/test_ollama.py \
  tests/unit/test_resources.py tests/component/test_redis.py

git commit -m "feat(cache): add redis client and health checks"
```

### Commit 5 — readiness and tracing

```bash
git add src/paperforge/api/ src/paperforge/core/logging.py \
  src/paperforge/core/request_context.py src/paperforge/middleware/ \
  src/paperforge/schemas/ src/paperforge/services/ \
  src/paperforge/main.py tests/unit/test_health_api.py \
  tests/unit/test_health_service.py tests/unit/test_logging.py \
  tests/unit/test_dependencies.py

git commit -m "feat(api): add readiness and request tracing middleware"
```

### Commit 6 — CI and documentation

```bash
git add .github/workflows/ci.yml README.md docs/WEEK1_CORE_INFRASTRUCTURE.md

git commit -m "docs: document week one infrastructure workflow"
```

## 13. Pull request

Push the branch:

```bash
git push -u origin week-1/core-infrastructure
```

Suggested PR title:

```text
Build migration-managed core infrastructure and readiness reporting
```

Include in the PR description:

- `make check` output.
- `make test-component` output.
- A readiness JSON example.
- A screenshot of Docker Compose services.
- A note that Redis/Ollama failures degrade rather than crash unrelated API
  routes.
- A note that schema creation is Alembic-only.

## Acceptance checklist

```text
[ ] uv.lock regenerated inside Linux
[ ] Docker Compose config validates
[ ] PostgreSQL, Redis, and OpenSearch become healthy
[ ] Alembic creates papers and alembic_version tables
[ ] No create_all() exists in src/
[ ] OpenSearch bootstrap is idempotent
[ ] Liveness returns HTTP 200 independently of dependencies
[ ] Readiness reports PostgreSQL, OpenSearch, Redis, and Ollama
[ ] Optional Redis outage produces degraded HTTP 200
[ ] Required OpenSearch outage produces not_ready HTTP 503
[ ] X-Request-ID is accepted or generated and returned
[ ] API logs are structured JSON
[ ] make check passes
[ ] make test-component passes
[ ] Data survives make down followed by make up-week1
[ ] GitHub Actions is green
[ ] Working tree is clean after commits
```
