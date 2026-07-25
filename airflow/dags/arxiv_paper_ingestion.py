"""Daily Week 4 ingestion, BM25 indexing, and hybrid chunk indexing DAG."""

import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from airflow.sdk import DAG, task

_PAPERFORGE_CLI = "/opt/paperforge/.venv/bin/paperforge"
_PDF_CACHE = Path("/workspace/data/arxiv_pdfs")


def _paperforge_environment() -> dict[str, str]:
    environment = os.environ.copy()
    environment.update(
        {
            "PAPERFORGE_ENVIRONMENT": "production",
            "PAPERFORGE_RELOAD": "false",
        }
    )
    return environment


@task
def ingest_previous_interval(day: str) -> None:
    """Ingest the arXiv date represented by the Airflow logical interval."""

    subprocess.run(
        [
            _PAPERFORGE_CLI,
            "ingest",
            "--from-date",
            day,
            "--to-date",
            day,
            "--fail-on-errors",
        ],
        check=True,
        env=_paperforge_environment(),
    )


@task
def index_search_documents(updated_since: str) -> None:
    """Synchronize newly created or updated PostgreSQL papers into OpenSearch."""

    subprocess.run(
        [
            _PAPERFORGE_CLI,
            "search-index",
            "--updated-since",
            updated_since,
            "--refresh",
            "--fail-on-errors",
        ],
        check=True,
        env=_paperforge_environment(),
    )


@task
def index_hybrid_chunks(updated_since: str) -> None:
    """Chunk and embed newly updated papers for Week 4 hybrid search."""

    subprocess.run(
        [
            _PAPERFORGE_CLI,
            "hybrid-index",
            "--updated-since",
            updated_since,
            "--refresh",
            "--fail-on-errors",
        ],
        check=True,
        env=_paperforge_environment(),
    )


@task
def report_pipeline_stats() -> None:
    """Emit PostgreSQL and both OpenSearch index counts into the task log."""

    environment = _paperforge_environment()
    subprocess.run([_PAPERFORGE_CLI, "stats"], check=True, env=environment)
    subprocess.run([_PAPERFORGE_CLI, "search-stats"], check=True, env=environment)
    subprocess.run([_PAPERFORGE_CLI, "hybrid-stats"], check=True, env=environment)


@task
def cleanup_old_pdf_cache() -> int:
    """Delete cached PDFs older than the configured retention period."""

    retention_days = int(os.getenv("PAPERFORGE_INGESTION__PDF_RETENTION_DAYS", "30"))
    cutoff = time.time() - retention_days * 24 * 60 * 60
    deleted = 0
    if not _PDF_CACHE.exists():
        return deleted
    for pdf_path in _PDF_CACHE.glob("*.pdf"):
        if pdf_path.stat().st_mtime < cutoff:
            pdf_path.unlink()
            deleted += 1
    return deleted


with DAG(
    dag_id="paperforge_arxiv_ingestion",
    description="Fetch, parse, persist, then index BM25 and RRF hybrid search",
    start_date=datetime(2026, 7, 24, tzinfo=UTC),
    schedule="0 6 * * 1-5",
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "paperforge",
        "retries": 2,
        "retry_delay": timedelta(minutes=30),
    },
    tags=["paperforge", "arxiv", "docling", "opensearch", "hybrid", "week4"],
) as dag:
    ingest = ingest_previous_interval("{{ ds_nodash }}")
    index = index_search_documents("{{ data_interval_start.isoformat() }}")
    hybrid = index_hybrid_chunks("{{ data_interval_start.isoformat() }}")
    report = report_pipeline_stats()
    cleanup = cleanup_old_pdf_cache()

    ingest >> index >> hybrid >> report >> cleanup
