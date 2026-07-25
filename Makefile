SHELL := /bin/bash
COMPOSE := docker compose
RUN_API := $(COMPOSE) run --rm --no-deps api
RUN_INGEST := $(COMPOSE) --profile core --profile search --profile ingestion run --rm ingestion

.DEFAULT_GOAL := help

.PHONY: help verify-host bootstrap build build-ingestion build-airflow build-runtime up up-infra up-week1 up-week2 up-week3 up-week4 up-airflow up-search-ui wait-infra migrate migration search-init infra-init down reset ps logs airflow-logs shell ingestion-shell sync sync-ingestion lock format format-check lint typecheck test test-cov test-component test-external test-docling check health readiness container-info compose-config ingest ingest-metadata ingest-date stats search-index search-rebuild search-stats search-query hybrid-index hybrid-index-text hybrid-rebuild hybrid-stats hybrid-query airflow-dags airflow-errors

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; printf "\nPaperforge Week 4 commands:\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

verify-host: ## Verify host tools; never installs Python
	@bash scripts/verify-host.sh

bootstrap: ## Build API image and sync lightweight dependencies
	@test -f .env || cp .env.example .env
	$(COMPOSE) build api
	@if test -f uv.lock; then \
		$(RUN_API) uv sync --frozen; \
	else \
		$(RUN_API) uv lock && $(RUN_API) uv sync --frozen; \
	fi

build: ## Build the lightweight API development image
	$(COMPOSE) build api

build-ingestion: ## Build the Linux image with Docling system libraries
	$(COMPOSE) --profile core --profile search --profile ingestion build ingestion

build-airflow: ## Build Airflow plus its isolated uv-managed Paperforge environment
	$(COMPOSE) --profile core --profile search --profile ingestion build airflow

build-runtime: ## Build immutable API production image
	@test -f uv.lock || (echo "uv.lock is missing; run make lock" && exit 1)
	docker build --target runtime --tag paperforge:local .

up: ## Start only the API; readiness may report missing infrastructure
	@test -f .env || cp .env.example .env
	$(COMPOSE) up --build -d api

up-infra: ## Start PostgreSQL, Redis, and OpenSearch
	@test -f .env || cp .env.example .env
	$(COMPOSE) --profile core --profile search up -d postgres redis opensearch
	@bash scripts/wait-for-infra.sh

up-week1: ## Start and initialize the complete Week 1 stack
	@$(MAKE) up-infra
	@$(MAKE) infra-init
	$(COMPOSE) up --build -d api

up-week2: ## Start Week 1 infrastructure, API, and prepare the ingestion environment
	@$(MAKE) up-week1
	@$(MAKE) build-ingestion
	@$(MAKE) sync-ingestion

up-week3: ## Start Week 2 and synchronize PostgreSQL papers into BM25 search
	@$(MAKE) up-week2
	@$(MAKE) search-index

up-week4: ## Start Week 3 and build the chunk-level hybrid index
	@$(MAKE) up-week3
	@$(MAKE) hybrid-index

up-airflow: ## Start local Airflow 3 standalone under the ingestion profile
	@test -f .env || cp .env.example .env
	$(COMPOSE) --profile core --profile search --profile ingestion up --build -d postgres opensearch airflow-db-init airflow

up-search-ui: ## Start OpenSearch and Dashboards
	$(COMPOSE) --profile search --profile search-ui up -d opensearch opensearch-dashboards

wait-infra: ## Wait until Week 1 infrastructure is healthy
	@bash scripts/wait-for-infra.sh

migrate: ## Apply Alembic migrations inside Linux
	$(RUN_API) uv run alembic upgrade head

migration: ## Create an Alembic migration; usage: make migration MSG="description"
	@test -n "$(MSG)" || (echo 'Usage: make migration MSG="description"' && exit 1)
	$(RUN_API) uv run alembic revision --autogenerate -m "$(MSG)"

search-init: ## Idempotently bootstrap the OpenSearch index
	$(RUN_API) uv run python -m paperforge.infrastructure.bootstrap

infra-init: ## Apply database migrations and search bootstrap
	@$(MAKE) migrate
	@$(MAKE) search-init

down: ## Stop all known services without deleting data
	$(COMPOSE) --profile core --profile search --profile search-ui --profile ingestion down

reset: ## Stop containers and delete every Paperforge volume
	$(COMPOSE) --profile core --profile search --profile search-ui --profile ingestion down --volumes --remove-orphans

ps: ## Show all service states
	$(COMPOSE) --profile core --profile search --profile search-ui --profile ingestion ps

logs: ## Follow API and Week 1 service logs
	$(COMPOSE) logs --follow api postgres redis opensearch

airflow-logs: ## Follow the local Airflow standalone logs
	$(COMPOSE) --profile core --profile search --profile ingestion logs --follow airflow

shell: ## Open a one-off lightweight Linux shell
	$(RUN_API) bash

ingestion-shell: ## Open a Linux shell with the ingestion venv mounted
	$(RUN_INGEST) bash

sync: ## Sync lightweight dependencies from committed uv.lock
	@test -f uv.lock || (echo "uv.lock is missing; run make lock" && exit 1)
	$(RUN_API) uv sync --frozen

sync-ingestion: ## Sync Docling and CPU-only PyTorch in the isolated ingestion venv
	@test -f uv.lock || (echo "uv.lock is missing; run make lock" && exit 1)
	$(RUN_INGEST) uv sync --frozen --extra ingestion

lock: ## Regenerate uv.lock inside Linux after dependency changes
	$(RUN_API) uv lock

format: ## Format Python source inside Linux
	$(RUN_API) uv run ruff format src tests migrations airflow

format-check: ## Check formatting inside Linux
	$(RUN_API) uv run ruff format --check src tests migrations airflow

lint: ## Lint source inside Linux
	$(RUN_API) uv run ruff check src tests migrations airflow

typecheck: ## Run strict mypy inside Linux
	$(RUN_API) uv run mypy src tests

test: ## Run unit tests inside Linux
	$(RUN_API) uv run pytest

test-cov: ## Run unit tests with coverage gate
	$(RUN_API) uv run pytest --cov=paperforge --cov-report=term-missing

test-component: ## Run tests against real Compose services
	@$(MAKE) up-infra
	@$(MAKE) infra-init
	$(RUN_API) uv run pytest -m component

test-external: ## Opt-in real arXiv API smoke test
	$(RUN_INGEST) uv run pytest -m external

test-docling: ## Opt-in one-paper end-to-end Docling run
	$(RUN_INGEST) uv run paperforge ingest --max-results 1 --force-download --fail-on-errors

check: format-check lint typecheck test-cov ## Run all lightweight quality gates

health: ## Check process liveness from the host
	@curl --fail --silent http://localhost:8000/api/v1/health/live && echo

readiness: ## Show dependency readiness from the host
	@curl --silent --show-error http://localhost:8000/api/v1/health/ready | $(COMPOSE) run --rm -T --no-deps api uv run python -m json.tool

container-info: ## Verify Python and uv are running on Linux
	$(RUN_API) bash scripts/verify-container.sh

compose-config: ## Validate all Week 4 Compose profiles
	$(COMPOSE) --profile core --profile search --profile search-ui --profile ingestion config --quiet

ingest: ## Fetch and parse papers; override with MAX_RESULTS=3
	$(RUN_INGEST) uv run paperforge ingest --max-results $(or $(MAX_RESULTS),3)

ingest-metadata: ## Fetch and upsert metadata without downloading PDFs
	$(RUN_INGEST) uv run paperforge ingest --metadata-only --max-results $(or $(MAX_RESULTS),3)

ingest-date: ## Ingest one date; usage: make ingest-date DATE=2026-07-23 MAX_RESULTS=3
	@test -n "$(DATE)" || (echo "Usage: make ingest-date DATE=YYYY-MM-DD [MAX_RESULTS=3]" && exit 1)
	$(RUN_INGEST) uv run paperforge ingest --from-date $(DATE) --to-date $(DATE) --max-results $(or $(MAX_RESULTS),3)

stats: ## Print PostgreSQL paper and processing counts
	$(RUN_INGEST) uv run paperforge stats

search-index: ## Upsert all PostgreSQL papers into the BM25 index
	$(RUN_API) uv run paperforge search-index --refresh --fail-on-errors

search-rebuild: ## Recreate only the derived search index and backfill it
	$(RUN_API) uv run paperforge search-index --rebuild --refresh --fail-on-errors

search-stats: ## Print OpenSearch BM25 index statistics
	$(RUN_API) uv run paperforge search-stats

search-query: ## Run BM25 search; usage: make search-query Q="AI agents"
	@test -n "$(Q)" || (echo 'Usage: make search-query Q="query"' && exit 1)
	$(RUN_API) uv run paperforge search "$(Q)"

hybrid-index: ## Chunk and embed all processed papers for Week 4
	$(RUN_API) uv run paperforge hybrid-index --refresh --fail-on-errors

hybrid-index-text: ## Build chunk BM25 documents without calling Jina
	$(RUN_API) uv run paperforge hybrid-index --text-only --refresh --fail-on-errors

hybrid-rebuild: ## Recreate only the Week 4 chunk index and RRF pipeline
	$(RUN_API) uv run paperforge hybrid-index --rebuild --refresh --fail-on-errors

hybrid-stats: ## Print chunk, vector, and unique-paper index statistics
	$(RUN_API) uv run paperforge hybrid-stats

hybrid-query: ## Unified search; usage: make hybrid-query Q="semantic retrieval" MODE=auto
	@test -n "$(Q)" || (echo 'Usage: make hybrid-query Q="query" [MODE=auto|bm25|vector|hybrid]' && exit 1)
	$(RUN_API) uv run paperforge hybrid-search "$(Q)" --mode $(or $(MODE),auto)

airflow-dags: ## List Airflow DAGs and verify the Week 4 DAG appears
	$(COMPOSE) --profile core --profile search --profile ingestion exec airflow airflow dags list

airflow-errors: ## List Airflow DAG import errors
	$(COMPOSE) --profile core --profile search --profile ingestion exec airflow airflow dags list-import-errors
