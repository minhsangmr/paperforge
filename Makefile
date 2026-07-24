SHELL := /bin/bash
COMPOSE := docker compose
RUN_API := $(COMPOSE) run --rm --no-deps api

.DEFAULT_GOAL := help

.PHONY: help verify-host bootstrap build build-runtime up up-core up-search down reset ps logs shell sync lock format format-check lint typecheck test test-cov check health container-info compose-config

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; printf "\nPaperforge Week 0 commands:\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-18s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

verify-host: ## Verify macOS host tools; never installs Python
	@bash scripts/verify-host.sh

bootstrap: ## Create .env, build Linux dev image, create lock if needed, and sync
	@test -f .env || cp .env.example .env
	$(COMPOSE) build api
	@if test -f uv.lock; then \
		$(RUN_API) uv sync --frozen; \
	else \
		$(RUN_API) uv lock && $(RUN_API) uv sync --frozen; \
	fi

build: ## Build the development image
	$(COMPOSE) build api

build-runtime: ## Build the immutable production target; requires uv.lock
	@test -f uv.lock || (echo "uv.lock is missing; run make bootstrap first" && exit 1)
	docker build --target runtime --tag paperforge:local .

up: ## Start only the Week 0 API
	$(COMPOSE) up --build -d api

up-core: ## Start API, PostgreSQL, and Redis
	$(COMPOSE) --profile core up --build -d api postgres redis

up-search: ## Start API and OpenSearch search profile
	$(COMPOSE) --profile search up --build -d api opensearch

down: ## Stop containers without deleting data
	$(COMPOSE) down

reset: ## Stop containers and delete project volumes
	$(COMPOSE) down --volumes --remove-orphans

ps: ## Show container status
	$(COMPOSE) ps

logs: ## Follow API logs
	$(COMPOSE) logs --follow api

shell: ## Open a one-off Linux shell
	$(RUN_API) bash

sync: ## Sync dependencies from committed uv.lock inside Linux
	@test -f uv.lock || (echo "uv.lock is missing; run make bootstrap first" && exit 1)
	$(RUN_API) uv sync --frozen

lock: ## Regenerate uv.lock inside Linux after dependency changes
	$(RUN_API) uv lock

format: ## Format source and tests inside Linux
	$(RUN_API) uv run ruff format src tests

format-check: ## Check formatting inside Linux
	$(RUN_API) uv run ruff format --check src tests

lint: ## Lint source and tests inside Linux
	$(RUN_API) uv run ruff check src tests

typecheck: ## Run strict mypy inside Linux
	$(RUN_API) uv run mypy src tests

test: ## Run unit tests inside Linux
	$(RUN_API) uv run pytest

test-cov: ## Run tests with coverage gate inside Linux
	$(RUN_API) uv run pytest --cov=paperforge --cov-report=term-missing

check: format-check lint typecheck test-cov ## Run every Week 0 quality gate

health: ## Check the running API from the Mac host
	@curl --fail --silent http://localhost:8000/api/v1/health/live && echo

container-info: ## Verify Python and uv are Linux-only
	$(RUN_API) bash scripts/verify-container.sh

compose-config: ## Validate the merged Compose model
	$(COMPOSE) config --quiet
