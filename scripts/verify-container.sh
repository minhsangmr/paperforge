#!/usr/bin/env bash
set -euo pipefail

printf 'Kernel:  %s\n' "$(uname -s)"
printf 'Arch:    %s\n' "$(uname -m)"
printf 'Python:  %s\n' "$(uv run python --version)"
printf 'uv:      %s\n' "$(uv --version)"
printf 'Project: %s\n' "$(pwd)"
printf 'Venv:    %s\n' "${VIRTUAL_ENV:-/workspace/.venv}"

test "$(uname -s)" = "Linux"
uv run python -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version'
uv run python -c 'import paperforge; print("Paperforge", paperforge.__version__)'
