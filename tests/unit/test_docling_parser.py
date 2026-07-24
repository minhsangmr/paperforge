"""Tests for the lazy Docling adapter."""

from pathlib import Path

import pytest

from paperforge.core.config import DocumentParserSettings
from paperforge.exceptions import DocumentValidationError
from paperforge.services.documents.docling_parser import DoclingDocumentParser


class _FakeDocument:
    def export_to_text(self) -> str:
        return "Introduction\nBody text\nConclusion\nFinal text"

    def export_to_markdown(self) -> str:
        return "# Introduction\nBody text\n## Conclusion\nFinal text"


class _FakeResult:
    document = _FakeDocument()


class _FakeConverter:
    def convert(self, *_: object, **__: object) -> _FakeResult:
        return _FakeResult()


@pytest.mark.asyncio
async def test_parser_extracts_heading_delimited_sections(tmp_path: Path) -> None:
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nfake")
    parser = DoclingDocumentParser(
        DocumentParserSettings(),
        converter_factory=_FakeConverter,
    )

    result = await parser.parse(pdf)

    assert result.parser_used == "docling"
    assert [section.title for section in result.sections] == ["Introduction", "Conclusion"]
    assert result.sections[1].level == 2
    assert result.parser_metadata["section_count"] == 2


def test_sections_fall_back_when_markdown_has_no_headings() -> None:
    sections = DoclingDocumentParser.sections_from_markdown("plain body", fallback="plain body")

    assert len(sections) == 1
    assert sections[0].title == "Content"
    assert sections[0].content == "plain body"


@pytest.mark.asyncio
async def test_parser_rejects_non_pdf_file(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_text("not a pdf")
    parser = DoclingDocumentParser(DocumentParserSettings(), converter_factory=_FakeConverter)

    with pytest.raises(DocumentValidationError, match="PDF header"):
        await parser.parse(path)


class _EmptyDocument:
    def export_to_text(self) -> str:
        return ""

    def export_to_markdown(self) -> str:
        return ""


class _EmptyResult:
    document = _EmptyDocument()


class _EmptyConverter:
    def convert(self, *_: object, **__: object) -> _EmptyResult:
        return _EmptyResult()


class _FailingConverter:
    def convert(self, *_: object, **__: object) -> None:
        raise RuntimeError("converter failure")


@pytest.mark.asyncio
async def test_parser_rejects_missing_pdf(tmp_path: Path) -> None:
    parser = DoclingDocumentParser(DocumentParserSettings(), converter_factory=_FakeConverter)

    with pytest.raises(DocumentValidationError, match="does not exist"):
        await parser.parse(tmp_path / "missing.pdf")


@pytest.mark.asyncio
async def test_parser_rejects_empty_pdf(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    path.touch()
    parser = DoclingDocumentParser(DocumentParserSettings(), converter_factory=_FakeConverter)

    with pytest.raises(DocumentValidationError, match="empty"):
        await parser.parse(path)


@pytest.mark.asyncio
async def test_parser_rejects_file_over_configured_limit(tmp_path: Path) -> None:
    path = tmp_path / "large.pdf"
    path.write_bytes(b"%PDF-" + b"x" * (1024 * 1024))
    parser = DoclingDocumentParser(
        DocumentParserSettings(max_file_size_mb=1),
        converter_factory=_FakeConverter,
    )

    with pytest.raises(DocumentValidationError, match="parser limit"):
        await parser.parse(path)


@pytest.mark.asyncio
async def test_parser_wraps_converter_failure(tmp_path: Path) -> None:
    from paperforge.exceptions import DocumentParsingError

    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4\nfake")
    parser = DoclingDocumentParser(
        DocumentParserSettings(),
        converter_factory=_FailingConverter,
    )

    with pytest.raises(DocumentParsingError, match="Docling failed"):
        await parser.parse(path)


@pytest.mark.asyncio
async def test_parser_rejects_empty_docling_text(tmp_path: Path) -> None:
    from paperforge.exceptions import DocumentParsingError

    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-1.4\nfake")
    parser = DoclingDocumentParser(
        DocumentParserSettings(),
        converter_factory=_EmptyConverter,
    )

    with pytest.raises(DocumentParsingError, match="returned no text"):
        await parser.parse(path)
