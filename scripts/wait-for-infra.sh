#!/usr/bin/env bash
set -euo pipefail

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

max_attempts="${MAX_ATTEMPTS:-60}"
sleep_seconds="${SLEEP_SECONDS:-2}"

wait_for() {
  local name="$1"
  shift
  local attempt
  for ((attempt = 1; attempt <= max_attempts; attempt++)); do
    if "$@" >/dev/null 2>&1; then
      printf '%s is ready\n' "$name"
      return 0
    fi
    sleep "$sleep_seconds"
  done
  printf 'Timed out waiting for %s\n' "$name" >&2
  return 1
}

wait_for PostgreSQL docker compose exec -T postgres pg_isready -U "${POSTGRES_USER:-paperforge}" -d "${POSTGRES_DB:-paperforge}"
wait_for Redis docker compose exec -T redis redis-cli ping
wait_for OpenSearch curl --fail --silent http://localhost:9200/_cluster/health
