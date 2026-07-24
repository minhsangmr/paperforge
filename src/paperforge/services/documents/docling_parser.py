"""Lazy Docling adapter with stable Markdown-based section extraction."""

import asyncio
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from paperforge.core.config import DocumentParserSettings
from paperforge.exceptions import DocumentParsingError, DocumentValidationError
from paperforge.schemas.papers import DocumentSection, ParsedDocument

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


class DoclingDocumentParser:
    """Convert scientific PDFs with Docling without importing it at API startup."""

    def __init__(
        self,
        settings: DocumentParserSettings,
        converter_factory: Callable[[], Any] | None = None,
    ) -> None:
        self._settings = settings
        self._converter_factory = converter_factory
        self._converter: Any | None = None

    async def parse(self, pdf_path: Path) -> ParsedDocument:
        """Validate and convert a PDF on a worker thread."""

        self._validate(pdf_path)
        return await asyncio.to_thread(self._parse_sync, pdf_path)

    def _parse_sync(self, pdf_path: Path) -> ParsedDocument:
        try:
            converter = self._get_converter()
            result = converter.convert(
                str(pdf_path),
                max_num_pages=self._settings.max_pages,
                max_file_size=self._settings.max_file_size_mb * 1024 * 1024,
            )
            document = result.document
            raw_text = str(document.export_to_text()).strip()
            markdown = str(document.export_to_markdown()).strip()
            if not raw_text:
                raise DocumentParsingError(f"Docling returned no text for {pdf_path.name}")
            sections = self.sections_from_markdown(markdown, fallback=raw_text)
            return ParsedDocument(
                raw_text=raw_text,
                sections=sections,
                parser_used="docling",
                parser_metadata={
                    "source_file": pdf_path.name,
                    "section_count": len(sections),
                    "markdown_characters": len(markdown),
                    "max_pages": self._settings.max_pages,
                },
            )
        except DocumentParsingError:
            raise
        except Exception as exc:
            raise DocumentParsingError(f"Docling failed for {pdf_path.name}: {exc}") from exc

    def _get_converter(self) -> Any:
        if self._converter is not None:
            return self._converter
        if self._converter_factory is not None:
            self._converter = self._converter_factory()
            return self._converter
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ImportError as exc:
            raise DocumentParsingError(
                "Docling is not installed; run `make sync-ingestion` inside Docker"
            ) from exc

        options = PdfPipelineOptions()
        options.do_ocr = self._settings.do_ocr
        options.do_table_structure = self._settings.do_table_structure
        self._converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        return self._converter

    def _validate(self, pdf_path: Path) -> None:
        if not pdf_path.is_file():
            raise DocumentValidationError(f"PDF does not exist: {pdf_path}")
        size = pdf_path.stat().st_size
        if size == 0:
            raise DocumentValidationError(f"PDF is empty: {pdf_path}")
        max_bytes = self._settings.max_file_size_mb * 1024 * 1024
        if size > max_bytes:
            raise DocumentValidationError(
                f"PDF exceeds parser limit: {size} bytes > {max_bytes} bytes"
            )
        with pdf_path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise DocumentValidationError(f"file does not have a PDF header: {pdf_path}")

    @staticmethod
    def sections_from_markdown(markdown: str, *, fallback: str) -> list[DocumentSection]:
        """Split Docling Markdown by headings without depending on internal Docling models."""

        sections: list[DocumentSection] = []
        title = "Content"
        level = 1
        content: list[str] = []

        def flush() -> None:
            body = "\n".join(content).strip()
            if body:
                sections.append(DocumentSection(title=title, content=body, level=level))

        for line in markdown.splitlines():
            match = _HEADING.match(line)
            if match is None:
                content.append(line)
                continue
            flush()
            title = match.group(2).strip()
            level = len(match.group(1))
            content = []
        flush()
        if sections:
            return sections
        return [DocumentSection(title="Content", content=fallback.strip(), level=1)]
