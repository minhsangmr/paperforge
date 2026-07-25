"""Unit tests for deterministic section-aware chunking."""

from paperforge.core.config import ChunkingSettings
from paperforge.schemas.hybrid_search import TextChunk
from paperforge.services.chunking import SectionAwareChunker


def test_chunker_prefers_sections_and_excludes_references() -> None:
    chunker = SectionAwareChunker(
        ChunkingSettings(chunk_size_words=8, overlap_words=2, min_chunk_words=3)
    )
    chunks = chunker.chunk_paper(
        arxiv_id="2607.00001",
        title="Hybrid Retrieval",
        abstract="A concise semantic search abstract.",
        raw_text="fallback should not be used",
        sections=[
            {
                "title": "Introduction",
                "level": 1,
                "content": "one two three four five six seven eight nine ten",
            },
            {"title": "References", "level": 1, "content": "ignored citation content"},
        ],
    )
    assert [chunk.section_title for chunk in chunks] == [
        "Abstract",
        "Introduction",
        "Introduction",
    ]
    assert chunks[1].text.endswith("one two three four five six seven eight")
    assert chunks[2].text.endswith("seven eight nine ten")
    assert all("References" not in chunk.text for chunk in chunks)


def _stable_chunks(chunker: SectionAwareChunker) -> list[TextChunk]:
    return chunker.chunk_paper(
        arxiv_id="2607.00002",
        title="Stable chunks",
        abstract="alpha beta gamma",
        raw_text="",
        sections=None,
    )


def test_chunk_ids_are_deterministic() -> None:
    chunker = SectionAwareChunker(
        ChunkingSettings(chunk_size_words=10, overlap_words=2, min_chunk_words=2)
    )
    first = _stable_chunks(chunker)
    second = _stable_chunks(chunker)
    assert [chunk.chunk_id for chunk in first] == [chunk.chunk_id for chunk in second]


def test_chunker_combines_small_sections_and_falls_back_to_raw_text() -> None:
    settings = ChunkingSettings(chunk_size_words=20, overlap_words=5, min_chunk_words=5)
    chunker = SectionAwareChunker(settings)
    combined = chunker.chunk_paper(
        arxiv_id="x",
        title="T",
        abstract="",
        raw_text="unused",
        sections=[
            {"title": "A", "content": "one two"},
            {"title": "B", "content": "three four five"},
        ],
    )
    assert len(combined) == 1
    assert combined[0].section_title == "A / B"

    fallback = chunker.chunk_paper(
        arxiv_id="y",
        title="T",
        abstract="",
        raw_text="one two three four five six",
        sections=[],
    )
    assert fallback[0].section_title == "Content"
