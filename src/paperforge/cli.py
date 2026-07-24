"""Container-only command line interface for ingestion operations."""

import argparse
import asyncio
import json
from datetime import date, datetime
from typing import NoReturn

from paperforge.core.config import Settings, get_settings
from paperforge.core.logging import configure_logging
from paperforge.exceptions import IngestionPipelineError
from paperforge.infrastructure.database import Database
from paperforge.repositories.paper import PaperRepository
from paperforge.services.arxiv.client import ArxivClient
from paperforge.services.documents.docling_parser import DoclingDocumentParser
from paperforge.services.ingestion import IngestionService


def _compact_date(value: str) -> str:
    """Accept YYYY-MM-DD or YYYYMMDD and return the arXiv form."""

    try:
        parsed = (
            date.fromisoformat(value) if "-" in value else datetime.strptime(value, "%Y%m%d").date()
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD or YYYYMMDD") from exc
    return parsed.strftime("%Y%m%d")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paperforge")
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest = subcommands.add_parser("ingest", help="fetch arXiv papers and store them")
    ingest.add_argument("--max-results", type=int)
    ingest.add_argument("--from-date", type=_compact_date)
    ingest.add_argument("--to-date", type=_compact_date)
    ingest.add_argument("--metadata-only", action="store_true")
    ingest.add_argument("--force-download", action="store_true")
    ingest.add_argument("--fail-on-errors", action="store_true")

    subcommands.add_parser("stats", help="print current paper persistence counts")
    return parser


async def _run_ingest(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database)
    arxiv = ArxivClient(settings.arxiv)
    parser = DoclingDocumentParser(settings.document_parser)
    service = IngestionService(arxiv, parser, settings.ingestion, settings.arxiv.category)
    try:
        with database.session() as session:
            report = await service.run(
                session,
                max_results=args.max_results,
                from_date=args.from_date,
                to_date=args.to_date,
                process_pdfs=not args.metadata_only,
                force_download=args.force_download,
            )
        payload = report.model_dump(mode="json")
        payload["papers_stored"] = report.papers_stored
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 1 if args.fail_on_errors and report.issues else 0
    except IngestionPipelineError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2
    finally:
        await arxiv.close()
        database.close()


def _run_stats(settings: Settings) -> int:
    database = Database(settings.database)
    try:
        with database.session() as session:
            stats = PaperRepository(session).stats()
        payload = {
            "total": stats.total,
            "processed": stats.processed,
            "with_text": stats.with_text,
        }
        print(json.dumps(payload, indent=2))
        return 0
    finally:
        database.close()


def main() -> NoReturn:
    """Parse CLI arguments and exit with a task-friendly status code."""

    args = _parser().parse_args()
    settings = get_settings()
    configure_logging(settings)
    code = (
        asyncio.run(_run_ingest(args, settings))
        if args.command == "ingest"
        else _run_stats(settings)
    )
    raise SystemExit(code)


if __name__ == "__main__":
    main()
