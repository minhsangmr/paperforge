SHELL := /bin/bash
COMPOSE := docker compose
RUN_API := $(COMPOSE) run --rm --no-deps api

.DEFAULT_GOAL := help

.PHONY: help verify-host bootstrap build build-runtime up up-infra up-week1 up-search-ui wait-infra migrate migration search-init infra-init down reset ps logs shell sync lock format format-check lint typecheck test test-cov test-component check health readiness container-info compose-config

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; printf "\nPaperforge Week 1 commands:\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

verify-host: ## Verify host tools; never installs Python
	@bash scripts/verify-host.sh

bootstrap: ## Build Linux image and sync dependencies
	@test -f .env || cp .env.example .env
	$(COMPOSE) build api
	@if test -f uv.lock; then \
		$(RUN_API) uv sync --frozen; \
	else \
		$(RUN_API) uv lock && $(RUN_API) uv sync --frozen; \
	fi

build: ## Build the development image
	$(COMPOSE) build api

build-runtime: ## Build immutable production image
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

down: ## Stop containers without deleting data
	$(COMPOSE) --profile core --profile search --profile search-ui down

reset: ## Stop containers and delete all project volumes
	$(COMPOSE) --profile core --profile search --profile search-ui down --volumes --remove-orphans

ps: ## Show container status
	$(COMPOSE) --profile core --profile search --profile search-ui ps

logs: ## Follow API and core service logs
	$(COMPOSE) logs --follow api postgres redis opensearch

shell: ## Open a one-off Linux shell
	$(RUN_API) bash

sync: ## Sync dependencies from committed uv.lock inside Linux
	@test -f uv.lock || (echo "uv.lock is missing; run make lock" && exit 1)
	$(RUN_API) uv sync --frozen

lock: ## Regenerate uv.lock inside Linux after dependency changes
	$(RUN_API) uv lock

format: ## Format Python source inside Linux
	$(RUN_API) uv run ruff format src tests migrations

format-check: ## Check formatting inside Linux
	$(RUN_API) uv run ruff format --check src tests migrations

lint: ## Lint source inside Linux
	$(RUN_API) uv run ruff check src tests migrations

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

check: format-check lint typecheck test-cov ## Run all local quality gates

health: ## Check process liveness from the host
	@curl --fail --silent http://localhost:8000/api/v1/health/live && echo

readiness: ## Show dependency readiness from the host
	@curl --silent --show-error http://localhost:8000/api/v1/health/ready | $(COMPOSE) run --rm -T --no-deps api uv run python -m json.tool

container-info: ## Verify Python and uv are running on Linux
	$(RUN_API) bash scripts/verify-container.sh

compose-config: ## Validate the Compose model
	$(COMPOSE) --profile core --profile search --profile search-ui config --quiet
