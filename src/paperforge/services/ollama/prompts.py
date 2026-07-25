"""Grounded prompt construction for academic-paper RAG."""

from dataclasses import dataclass

from paperforge.schemas.hybrid_search import HybridSearchHit
from paperforge.schemas.rag import RAGSource

SYSTEM_PROMPT = """You answer questions using only the supplied academic-paper excerpts.

Rules:
1. Do not use outside knowledge or invent missing facts.
2. Cite claims with the supplied source labels, for example [S1] or [S1][S2].
3. State clearly when the excerpts are insufficient or conflicting.
4. Prefer concise synthesis over repeating every excerpt.
5. Do not include a bibliography; source links are returned separately.
6. Keep the answer under {max_words} words.
"""


@dataclass(frozen=True, slots=True)
class PromptBundle:
    """Prompt text plus the exact sources represented in its context."""

    prompt: str
    sources: list[RAGSource]


class RAGPromptBuilder:
    """Build bounded prompts with stable citation labels."""

    def __init__(self, *, max_context_characters: int, max_answer_words: int) -> None:
        self._max_context_characters = max_context_characters
        self._max_answer_words = max_answer_words

    def build(self, query: str, hits: list[HybridSearchHit]) -> PromptBundle:
        """Create a grounded prompt and omit context that exceeds the configured limit."""

        remaining = self._max_context_characters
        blocks: list[str] = []
        sources: list[RAGSource] = []
        for hit in hits:
            citation = f"S{len(sources) + 1}"
            header = (
                f"[{citation}] {hit.title}\narXiv: {hit.arxiv_id}\nSection: {hit.section_title}\n"
            )
            available = remaining - len(header)
            if available <= 0:
                break
            excerpt = hit.chunk_text.strip()[:available]
            if not excerpt:
                continue
            block = f"{header}Excerpt: {excerpt}"
            blocks.append(block)
            remaining -= len(block)
            sources.append(
                RAGSource(
                    citation=citation,
                    arxiv_id=hit.arxiv_id,
                    title=hit.title,
                    pdf_url=hit.pdf_url,
                    section_title=hit.section_title,
                    chunk_id=hit.chunk_id,
                )
            )
            if remaining <= 0:
                break

        context = "\n\n".join(blocks) or "No relevant excerpts were retrieved."
        prompt = (
            SYSTEM_PROMPT.format(max_words=self._max_answer_words)
            + "\n\nCONTEXT\n"
            + context
            + "\n\nQUESTION\n"
            + query
            + "\n\nANSWER\n"
        )
        return PromptBundle(prompt=prompt, sources=sources)
