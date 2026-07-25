"""Tests for bounded, citeable RAG prompt construction."""

from datetime import UTC, datetime

from paperforge.schemas.hybrid_search import HybridSearchHit
from paperforge.services.ollama.prompts import RAGPromptBuilder


def _hit(chunk_id: str, text: str) -> HybridSearchHit:
    return HybridSearchHit(
        chunk_id=chunk_id,
        chunk_index=0,
        arxiv_id="2607.00001",
        title="Grounded Retrieval",
        authors=["Ada Lovelace"],
        abstract="abstract",
        categories=["cs.IR"],
        published_date=datetime.now(UTC),
        pdf_url="https://arxiv.org/pdf/2607.00001.pdf",
        section_title="Methods",
        chunk_text=text,
        score=1.0,
    )


def test_prompt_assigns_stable_source_labels() -> None:
    bundle = RAGPromptBuilder(max_context_characters=2000, max_answer_words=300).build(
        "What is grounded retrieval?",
        [_hit("c1", "First excerpt."), _hit("c2", "Second excerpt.")],
    )

    assert "[S1] Grounded Retrieval" in bundle.prompt
    assert "[S2] Grounded Retrieval" in bundle.prompt
    assert [source.citation for source in bundle.sources] == ["S1", "S2"]
    assert "Do not use outside knowledge" in bundle.prompt


def test_prompt_respects_context_character_limit() -> None:
    bundle = RAGPromptBuilder(max_context_characters=120, max_answer_words=100).build(
        "Question",
        [_hit("c1", "x" * 500), _hit("c2", "y" * 500)],
    )

    assert len(bundle.sources) == 1
    assert "y" * 10 not in bundle.prompt
