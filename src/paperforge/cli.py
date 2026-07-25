"""Container-only command line interface for ingestion and search operations."""

import argparse
import asyncio
import json
from datetime import UTC, date, datetime
from typing import NoReturn

from paperforge.core.config import Settings, get_settings
from paperforge.core.logging import configure_logging
from paperforge.exceptions import IngestionPipelineError, SearchIndexSchemaError
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.hybrid_search import HybridSearchRequest
from paperforge.schemas.search import SearchRequest
from paperforge.services.arxiv.client import ArxivClient
from paperforge.services.chunking import SectionAwareChunker
from paperforge.services.documents.docling_parser import DoclingDocumentParser
from paperforge.services.embeddings.jina import JinaEmbeddingsClient
from paperforge.services.hybrid_indexing import HybridIndexingService
from paperforge.services.hybrid_search import HybridSearchService
from paperforge.services.ingestion import IngestionService
from paperforge.services.search_indexing import SearchIndexingService


def _compact_date(value: str) -> str:
    """Accept YYYY-MM-DD or YYYYMMDD and return the arXiv form."""

    try:
        parsed = (
            date.fromisoformat(value) if "-" in value else datetime.strptime(value, "%Y%m%d").date()
        )
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD or YYYYMMDD") from exc
    return parsed.strftime("%Y%m%d")


def _iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("date must be YYYY-MM-DD") from exc


def _iso_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("datetime must be ISO 8601") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


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

    subcommands.add_parser("stats", help="print current PostgreSQL paper counts")

    index = subcommands.add_parser(
        "search-index",
        help="synchronize PostgreSQL papers into the Week 3 BM25 index",
    )
    index.add_argument("--batch-size", type=int)
    index.add_argument("--updated-since", type=_iso_datetime)
    index.add_argument("--processed-only", action="store_true")
    index.add_argument("--refresh", action="store_true")
    index.add_argument("--rebuild", action="store_true")
    index.add_argument("--fail-on-errors", action="store_true")

    subcommands.add_parser("search-stats", help="print OpenSearch index statistics")

    search = subcommands.add_parser("search", help="run a BM25 query from the container")
    search.add_argument("query")
    search.add_argument("--category", action="append", default=[])
    search.add_argument("--published-from", type=_iso_date)
    search.add_argument("--published-to", type=_iso_date)
    search.add_argument("--processed-only", action="store_true")
    search.add_argument("--page", type=int, default=1)
    search.add_argument("--page-size", type=int)
    search.add_argument(
        "--sort",
        choices=["relevance", "published_desc", "published_asc"],
        default="relevance",
    )

    hybrid_index = subcommands.add_parser(
        "hybrid-index",
        help="chunk processed papers and synchronize the Week 4 vector index",
    )
    hybrid_index.add_argument("--batch-size", type=int)
    hybrid_index.add_argument("--updated-since", type=_iso_datetime)
    hybrid_index.add_argument("--refresh", action="store_true")
    hybrid_index.add_argument("--rebuild", action="store_true")
    hybrid_index.add_argument(
        "--text-only",
        action="store_true",
        help="index chunks without calling the embedding provider",
    )
    hybrid_index.add_argument("--fail-on-errors", action="store_true")

    subcommands.add_parser("hybrid-stats", help="print Week 4 hybrid-index statistics")

    hybrid_search = subcommands.add_parser(
        "hybrid-search",
        help="run BM25, vector, or RRF hybrid search from the container",
    )
    hybrid_search.add_argument("query")
    hybrid_search.add_argument(
        "--mode", choices=["auto", "bm25", "vector", "hybrid"], default="auto"
    )
    hybrid_search.add_argument("--category", action="append", default=[])
    hybrid_search.add_argument("--published-from", type=_iso_date)
    hybrid_search.add_argument("--published-to", type=_iso_date)
    hybrid_search.add_argument("--page", type=int, default=1)
    hybrid_search.add_argument("--page-size", type=int)
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
        print(
            json.dumps(
                {
                    "total": stats.total,
                    "processed": stats.processed,
                    "with_text": stats.with_text,
                },
                indent=2,
            )
        )
        return 0
    finally:
        database.close()


def _run_search_index(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database)
    client = OpenSearchClient(settings.opensearch)
    try:
        with database.session() as session:
            report = SearchIndexingService(PaperRepository(session), client).run(
                batch_size=args.batch_size or settings.opensearch.bulk_batch_size,
                rebuild=args.rebuild,
                refresh=args.refresh,
                updated_since=args.updated_since,
                processed_only=args.processed_only,
            )
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 1 if args.fail_on_errors and report.failed else 0
    except SearchIndexSchemaError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}))
        return 2
    finally:
        client.close()
        database.close()


def _run_search_stats(settings: Settings) -> int:
    client = OpenSearchClient(settings.opensearch)
    try:
        print(json.dumps(client.stats().model_dump(mode="json"), indent=2))
        return 0
    finally:
        client.close()


def _run_search(args: argparse.Namespace, settings: Settings) -> int:
    client = OpenSearchClient(settings.opensearch)
    try:
        request = SearchRequest(
            query=args.query,
            categories=args.category,
            published_from=args.published_from,
            published_to=args.published_to,
            processed_only=args.processed_only,
            page=args.page,
            page_size=args.page_size or settings.opensearch.default_page_size,
            sort=args.sort,
        )
        response = client.search(request)
        print(json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0
    finally:
        client.close()


async def _run_hybrid_index(args: argparse.Namespace, settings: Settings) -> int:
    database = Database(settings.database)
    client = HybridSearchClient(settings.opensearch, settings.hybrid_search, settings.embeddings)
    embeddings = JinaEmbeddingsClient(settings.embeddings)
    try:
        with database.session() as session:
            report = await HybridIndexingService(
                PaperRepository(session),
                SectionAwareChunker(settings.chunking),
                embeddings,
                client,
            ).run(
                batch_size=args.batch_size or settings.hybrid_search.bulk_batch_size,
                rebuild=args.rebuild,
                refresh=args.refresh,
                updated_since=args.updated_since,
                embed=not args.text_only,
            )
        print(json.dumps(report.model_dump(mode="json"), indent=2))
        return 1 if args.fail_on_errors and report.failed else 0
    finally:
        await embeddings.close()
        client.close()
        database.close()


def _run_hybrid_stats(settings: Settings) -> int:
    client = HybridSearchClient(settings.opensearch, settings.hybrid_search, settings.embeddings)
    try:
        print(json.dumps(client.stats().model_dump(mode="json"), indent=2))
        return 0
    finally:
        client.close()


async def _run_hybrid_search(args: argparse.Namespace, settings: Settings) -> int:
    client = HybridSearchClient(settings.opensearch, settings.hybrid_search, settings.embeddings)
    embeddings = JinaEmbeddingsClient(settings.embeddings)
    try:
        request = HybridSearchRequest(
            query=args.query,
            mode=args.mode,
            categories=args.category,
            published_from=args.published_from,
            published_to=args.published_to,
            page=args.page,
            page_size=args.page_size or settings.hybrid_search.default_page_size,
        )
        response = await HybridSearchService(client, embeddings, settings.hybrid_search).search(
            request
        )
        print(json.dumps(response.model_dump(mode="json"), indent=2, ensure_ascii=False))
        return 0
    finally:
        await embeddings.close()
        client.close()


def main() -> NoReturn:
    """Parse CLI arguments and exit with a task-friendly status code."""

    args = _parser().parse_args()
    settings = get_settings()
    configure_logging(settings)
    if args.command == "ingest":
        code = asyncio.run(_run_ingest(args, settings))
    elif args.command == "stats":
        code = _run_stats(settings)
    elif args.command == "search-index":
        code = _run_search_index(args, settings)
    elif args.command == "search-stats":
        code = _run_search_stats(settings)
    elif args.command == "hybrid-index":
        code = asyncio.run(_run_hybrid_index(args, settings))
    elif args.command == "hybrid-stats":
        code = _run_hybrid_stats(settings)
    elif args.command == "hybrid-search":
        code = asyncio.run(_run_hybrid_search(args, settings))
    else:
        code = _run_search(args, settings)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
