"""PostgreSQL-to-OpenSearch chunking and embedding pipeline."""

from datetime import datetime

from paperforge.infrastructure.hybrid_search import HybridSearchClient
from paperforge.models.paper import Paper
from paperforge.repositories.paper import PaperRepository
from paperforge.schemas.hybrid_search import HybridChunkDocument, HybridIndexReport, TextChunk
from paperforge.services.chunking import SectionAwareChunker
from paperforge.services.embeddings.jina import JinaEmbeddingsClient


class HybridIndexingService:
    """Chunk processed papers, optionally embed them, and replace stale chunks."""

    def __init__(
        self,
        repository: PaperRepository,
        chunker: SectionAwareChunker,
        embeddings: JinaEmbeddingsClient,
        client: HybridSearchClient,
    ) -> None:
        self._repository = repository
        self._chunker = chunker
        self._embeddings = embeddings
        self._client = client

    async def run(
        self,
        *,
        batch_size: int,
        rebuild: bool = False,
        refresh: bool = False,
        updated_since: datetime | None = None,
        embed: bool = True,
    ) -> HybridIndexReport:
        """Build the index and synchronize all eligible processed papers."""

        if rebuild:
            self._client.recreate_index()
        else:
            self._client.ensure_index()

        papers_attempted = 0
        papers_indexed = 0
        papers_skipped = 0
        chunks_created = 0
        chunks_indexed = 0
        failed = 0
        errors: list[str] = []

        for papers in self._repository.iter_for_search_index(
            batch_size=batch_size,
            updated_since=updated_since,
            processed_only=True,
        ):
            for paper in papers:
                papers_attempted += 1
                try:
                    chunks = self._chunker.chunk_paper(
                        arxiv_id=paper.arxiv_id,
                        title=paper.title,
                        abstract=paper.abstract,
                        raw_text=paper.raw_text or "",
                        sections=paper.sections,
                    )
                    if not chunks:
                        papers_skipped += 1
                        continue
                    documents = await self._documents_for_paper(paper, chunks, embed=embed)
                    result = self._client.bulk_index(documents, refresh=refresh)
                    chunks_created += len(chunks)
                    chunks_indexed += result.indexed
                    failed += result.failed
                    errors.extend(result.errors)
                    if result.failed:
                        errors.append(f"{paper.arxiv_id}: {result.failed} chunk documents failed")
                    else:
                        self._client.delete_stale_paper_chunks(
                            paper.arxiv_id,
                            keep_chunk_ids=[document.chunk_id for document in documents],
                        )
                        papers_indexed += 1
                except Exception as exc:
                    failed += 1
                    errors.append(f"{paper.arxiv_id}: {exc}")

        return HybridIndexReport(
            index_name=self._client.settings.index_name,
            rebuilt=rebuild,
            embeddings_enabled=embed,
            papers_attempted=papers_attempted,
            papers_indexed=papers_indexed,
            papers_skipped=papers_skipped,
            chunks_created=chunks_created,
            chunks_indexed=chunks_indexed,
            failed=failed,
            errors=errors,
        )

    async def _documents_for_paper(
        self,
        paper: Paper,
        chunks: list[TextChunk],
        *,
        embed: bool,
    ) -> list[HybridChunkDocument]:
        vectors = (
            await self._embeddings.embed_passages([chunk.text for chunk in chunks])
            if embed
            else [None] * len(chunks)
        )
        if len(vectors) != len(chunks):
            raise ValueError("embedding count does not match chunk count")
        documents: list[HybridChunkDocument] = []
        for chunk, vector in zip(chunks, vectors, strict=True):
            documents.append(
                HybridChunkDocument(
                    chunk_id=chunk.chunk_id,
                    chunk_index=chunk.chunk_index,
                    paper_id=str(paper.id),
                    arxiv_id=paper.arxiv_id,
                    title=paper.title,
                    authors=paper.authors,
                    abstract=paper.abstract,
                    categories=paper.categories,
                    published_date=paper.published_date,
                    pdf_url=paper.pdf_url,
                    section_title=chunk.section_title,
                    section_level=chunk.section_level,
                    chunk_text=chunk.text,
                    chunk_word_count=chunk.word_count,
                    has_embedding=vector is not None,
                    embedding_model=self._embeddings.settings.model if vector is not None else None,
                    embedding=vector,
                    updated_at=paper.updated_at,
                )
            )
        return documents
