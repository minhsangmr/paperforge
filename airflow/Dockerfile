# syntax=docker/dockerfile:1.7

ARG AIRFLOW_VERSION=3.3.0
ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.10.0

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv
FROM apache/airflow:${AIRFLOW_VERSION}-python${PYTHON_VERSION}

USER root
COPY --from=uv /uv /uvx /usr/local/bin/
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /opt/paperforge /workspace/data/arxiv_pdfs /workspace/.cache/models \
    && chown -R airflow:0 /opt/paperforge /workspace

USER airflow
WORKDIR /opt/paperforge
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PATH="/opt/paperforge/.venv/bin:$PATH" \
    HF_HOME="/workspace/.cache/models/huggingface" \
    TORCH_HOME="/workspace/.cache/models/torch"

COPY --chown=airflow:0 pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/home/airflow/.cache/uv,uid=50000,gid=0 \
    uv sync --frozen --no-dev --extra ingestion --no-install-project

COPY --chown=airflow:0 src ./src
RUN --mount=type=cache,target=/home/airflow/.cache/uv,uid=50000,gid=0 \
    uv sync --frozen --no-dev --extra ingestion --no-editable

COPY --chown=airflow:0 airflow/dags /opt/airflow/dags
