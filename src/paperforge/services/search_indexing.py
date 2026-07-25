"""PostgreSQL-to-OpenSearch paper-level indexing."""

from datetime import datetime

from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.search import PaperSearchDocument, SearchIndexReport


class SearchIndexingService:
    """Project stored papers into the versioned Week 3 BM25 index."""

    def __init__(
        self,
        repository: PaperRepository,
        client: OpenSearchClient,
    ) -> None:
        self._repository = repository
        self._client = client

    def run(
        self,
        *,
        batch_size: int,
        rebuild: bool = False,
        refresh: bool = False,
        updated_since: datetime | None = None,
        processed_only: bool = False,
    ) -> SearchIndexReport:
        """Create or rebuild the index, then bulk-upsert database records."""

        if rebuild:
            self._client.recreate_index()
        else:
            self._client.ensure_index()

        batches = 0
        attempted = 0
        indexed = 0
        failed = 0
        errors: list[str] = []
        for papers in self._repository.iter_for_search_index(
            batch_size=batch_size,
            updated_since=updated_since,
            processed_only=processed_only,
        ):
            batches += 1
            documents = [self._to_document(paper) for paper in papers]
            result = self._client.bulk_index(documents, refresh=refresh)
            attempted += result.attempted
            indexed += result.indexed
            failed += result.failed
            errors.extend(result.errors)

        return SearchIndexReport(
            index_name=self._client.settings.index_name,
            rebuilt=rebuild,
            batches=batches,
            attempted=attempted,
            indexed=indexed,
            failed=failed,
            errors=errors,
        )

    @staticmethod
    def _to_document(paper: Paper) -> PaperSearchDocument:
        return PaperSearchDocument(
            id=str(paper.id),
            arxiv_id=paper.arxiv_id,
            title=paper.title,
            authors=paper.authors,
            abstract=paper.abstract,
            categories=paper.categories,
            published_date=paper.published_date,
            pdf_url=paper.pdf_url,
            raw_text=paper.raw_text or "",
            pdf_processed=paper.pdf_processed,
            created_at=paper.created_at,
            updated_at=paper.updated_at,
        )
