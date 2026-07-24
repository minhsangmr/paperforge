# syntax=docker/dockerfile:1.7

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.10.0

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim-bookworm AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
    bash \
    ca-certificates \
    curl \
    git \
    make \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# The dev target intentionally does not install dependencies at image-build time.
# Source code is bind-mounted and `make bootstrap` creates uv.lock + .venv in Linux.
FROM base AS dev

ENV PAPERFORGE_ENVIRONMENT=development \
    PAPERFORGE_HOST=0.0.0.0 \
    PAPERFORGE_PORT=8000 \
    PAPERFORGE_RELOAD=true

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "paperforge.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--no-access-log"]

# This target is built only after uv.lock exists and is committed.
FROM base AS builder

COPY pyproject.toml uv.lock README.md LICENSE ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-project

COPY src ./src

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable

FROM python:${PYTHON_VERSION}-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/workspace/.venv/bin:$PATH"

RUN groupadd --system paperforge \
    && useradd --system --gid paperforge --create-home paperforge

WORKDIR /workspace

COPY --from=builder --chown=paperforge:paperforge /workspace/.venv /workspace/.venv
COPY --from=builder --chown=paperforge:paperforge /workspace/src /workspace/src

USER paperforge

EXPOSE 8000

CMD ["uvicorn", "paperforge.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
