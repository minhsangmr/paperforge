#!/usr/bin/env bash
set -euo pipefail

failures=0

check_command() {
  local command_name="$1"
  if command -v "$command_name" >/dev/null 2>&1; then
    printf 'OK   %-18s %s\n' "$command_name" "$(command -v "$command_name")"
  else
    printf 'MISS %-18s not found\n' "$command_name"
    failures=$((failures + 1))
  fi
}

printf 'Paperforge host verification\n'
printf '%s\n' '------------------------------'
printf 'OS:   %s\n' "$(sw_vers -productVersion 2>/dev/null || uname -s)"
printf 'Arch: %s\n' "$(uname -m)"

check_command git
check_command docker
check_command code
check_command make

if command -v docker >/dev/null 2>&1; then
  if docker info >/dev/null 2>&1; then
    printf 'OK   %-18s reachable\n' 'Docker daemon'
  else
    printf 'MISS %-18s start Docker Desktop\n' 'Docker daemon'
    failures=$((failures + 1))
  fi

  if docker compose version >/dev/null 2>&1; then
    printf 'OK   %-18s %s\n' 'Docker Compose' "$(docker compose version --short)"
  else
    printf 'MISS %-18s plugin unavailable\n' 'Docker Compose'
    failures=$((failures + 1))
  fi
fi

if command -v python >/dev/null 2>&1 || command -v uv >/dev/null 2>&1; then
  printf '\nNOTE: Host Python/uv may exist, but Paperforge commands must not use them.\n'
fi

if (( failures > 0 )); then
  printf '\nHost verification failed with %d missing requirement(s).\n' "$failures"
  exit 1
fi

printf '\nHost is ready. Next command: make bootstrap\n'
