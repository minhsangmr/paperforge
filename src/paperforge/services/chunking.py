"""Deterministic section-aware text chunking."""

import hashlib
import re
from collections.abc import Iterable
from typing import Any

from paperforge.core.config import ChunkingSettings
from paperforge.schemas.hybrid_search import TextChunk

_WORD = re.compile(r"\S+")


class SectionAwareChunker:
    """Prefer Docling sections and fall back to overlapping raw-text windows."""

    def __init__(self, settings: ChunkingSettings) -> None:
        self._settings = settings
        self._excluded = {value.casefold() for value in settings.excluded_section_titles}

    def chunk_paper(
        self,
        *,
        arxiv_id: str,
        title: str,
        abstract: str,
        raw_text: str,
        sections: list[dict[str, Any]] | None,
    ) -> list[TextChunk]:
        """Create deterministic chunks with title context and stable identifiers."""

        candidates: list[tuple[str, int, str]] = []
        if abstract.strip():
            candidates.append(("Abstract", 1, abstract.strip()))

        normalized_sections = self._normalize_sections(sections or [])
        if normalized_sections:
            candidates.extend(normalized_sections)
        elif raw_text.strip():
            candidates.append(("Content", 1, raw_text.strip()))

        chunk_payloads: list[tuple[str, int, str]] = []
        small_buffer: list[tuple[str, int, str]] = []
        small_words = 0

        def flush_small() -> None:
            nonlocal small_buffer, small_words
            if not small_buffer:
                return
            section_title = " / ".join(item[0] for item in small_buffer)
            section_level = min(item[1] for item in small_buffer)
            content = "\n\n".join(f"Section: {name}\n{body}" for name, _, body in small_buffer)
            chunk_payloads.extend(self._split_section(title, section_title, section_level, content))
            small_buffer = []
            small_words = 0

        for section_title, section_level, content in candidates:
            word_count = len(self._words(content))
            if word_count < self._settings.min_chunk_words:
                small_buffer.append((section_title, section_level, content))
                small_words += word_count
                if small_words >= self._settings.min_chunk_words:
                    flush_small()
                continue
            flush_small()
            chunk_payloads.extend(self._split_section(title, section_title, section_level, content))
        flush_small()

        chunks: list[TextChunk] = []
        for index, (section_title, level, text) in enumerate(chunk_payloads):
            words = self._words(text)
            if not words:
                continue
            digest = hashlib.sha256(
                f"{arxiv_id}|{index}|{section_title}|{text}".encode()
            ).hexdigest()[:20]
            chunks.append(
                TextChunk(
                    chunk_id=f"{arxiv_id}:{index}:{digest}",
                    chunk_index=index,
                    section_title=section_title,
                    section_level=level,
                    text=text,
                    word_count=len(words),
                )
            )
        return chunks

    def _normalize_sections(self, sections: Iterable[dict[str, Any]]) -> list[tuple[str, int, str]]:
        normalized: list[tuple[str, int, str]] = []
        for index, section in enumerate(sections, start=1):
            title = str(
                section.get("title") or section.get("heading") or f"Section {index}"
            ).strip()
            content = str(section.get("content") or section.get("text") or "").strip()
            if not content or title.casefold() in self._excluded:
                continue
            raw_level = section.get("level", 1)
            level = (
                int(raw_level)
                if isinstance(raw_level, (int, str)) and str(raw_level).isdigit()
                else 1
            )
            normalized.append((title, min(max(level, 1), 6), content))
        return normalized

    def _split_section(
        self,
        paper_title: str,
        section_title: str,
        section_level: int,
        content: str,
    ) -> list[tuple[str, int, str]]:
        words = self._words(content)
        if not words:
            return []
        window = self._settings.chunk_size_words
        overlap = self._settings.overlap_words
        step = window - overlap
        payloads: list[tuple[str, int, str]] = []
        for start in range(0, len(words), step):
            body_words = words[start : start + window]
            if not body_words:
                break
            suffix = "" if start == 0 else f" (continued {start // step + 1})"
            text = (
                f"Title: {paper_title.strip()}\n"
                f"Section: {section_title}{suffix}\n\n"
                f"{' '.join(body_words)}"
            ).strip()
            payloads.append((section_title, section_level, text))
            if start + window >= len(words):
                break
        return payloads

    @staticmethod
    def _words(text: str) -> list[str]:
        return _WORD.findall(text)
