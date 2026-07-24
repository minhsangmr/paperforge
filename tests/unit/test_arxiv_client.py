"""Tests for the arXiv Atom client and PDF cache."""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from paperforge.core.config import ArxivSettings
from paperforge.exceptions import ArxivParseError, ArxivResponseError, PdfDownloadError
from paperforge.schemas.papers import ArxivPaper
from paperforge.services.arxiv.client import ArxivClient

ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2607.01234v1</id>
    <published>2026-07-20T12:00:00Z</published>
    <title>  A\n useful   paper </title>
    <summary> A structured\n abstract. </summary>
    <author><name>Alice Example</name></author>
    <author><name>Bob Example</name></author>
    <category term="cs.AI" />
    <category term="cs.LG" />
    <link href="http://arxiv.org/pdf/2607.01234v1" type="application/pdf" />
  </entry>
</feed>
"""


def test_parse_atom_feed_normalizes_metadata() -> None:
    papers = ArxivClient.parse_atom_feed(ATOM_FEED)

    assert len(papers) == 1
    paper = papers[0]
    assert paper.arxiv_id == "2607.01234v1"
    assert paper.title == "A useful paper"
    assert paper.abstract == "A structured abstract."
    assert paper.authors == ["Alice Example", "Bob Example"]
    assert paper.categories == ["cs.AI", "cs.LG"]
    assert paper.pdf_url == "https://arxiv.org/pdf/2607.01234v1"
    assert paper.published_date == datetime(2026, 7, 20, 12, tzinfo=UTC)


def test_parse_atom_feed_rejects_invalid_xml() -> None:
    with pytest.raises(ArxivParseError, match="invalid arXiv Atom XML"):
        ArxivClient.parse_atom_feed("<not-closed>")


@pytest.mark.asyncio
async def test_fetch_papers_uses_configured_query() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, text=ATOM_FEED)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(
            ArxivSettings(max_retries=1, user_agent="paperforge-tests"),
            client=http_client,
        )
        papers = await client.fetch_papers(
            max_results=2,
            from_date="20260720",
            to_date="20260721",
        )

    assert len(papers) == 1
    assert captured is not None
    assert captured.headers["user-agent"] == "paperforge-tests"
    assert captured.url.params["max_results"] == "2"
    assert "cat:cs.AI" in captured.url.params["search_query"]
    assert "submittedDate:[202607200000 TO 202607212359]" in captured.url.params["search_query"]


@pytest.mark.asyncio
async def test_download_pdf_is_atomic_and_then_uses_cache(tmp_path: Path) -> None:
    paper = ArxivPaper(
        arxiv_id="2607.01234v1",
        title="Paper",
        authors=["Alice"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 20, tzinfo=UTC),
        pdf_url="https://arxiv.org/pdf/2607.01234v1",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-1.4\nvalid-test-pdf")

    settings = ArxivSettings(
        pdf_cache_dir=tmp_path,
        max_retries=1,
        rate_limit_seconds=3,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(settings, client=http_client)
        first = await client.download_pdf(paper)
        second = await client.download_pdf(paper)

    assert first.cache_hit is False
    assert second.cache_hit is True
    assert first.path == second.path
    assert first.path.read_bytes().startswith(b"%PDF-")
    assert not first.path.with_suffix(".pdf.part").exists()


@pytest.mark.asyncio
async def test_download_pdf_rejects_non_pdf_content(tmp_path: Path) -> None:
    paper = ArxivPaper(
        arxiv_id="2607.01234v1",
        title="Paper",
        authors=["Alice"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 20, tzinfo=UTC),
        pdf_url="https://arxiv.org/pdf/2607.01234v1",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>not a pdf</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(
            ArxivSettings(pdf_cache_dir=tmp_path, max_retries=1),
            client=http_client,
        )
        with pytest.raises(PdfDownloadError, match="not a PDF"):
            await client.download_pdf(paper)


@pytest.mark.asyncio
async def test_fetch_paper_by_id_returns_first_match() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["id_list"] == "2607.01234v1"
        return httpx.Response(200, text=ATOM_FEED)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(
            ArxivSettings(max_retries=1, user_agent="paperforge-tests"),
            client=http_client,
        )
        paper = await client.fetch_paper_by_id("2607.01234v1")

    assert paper is not None
    assert paper.arxiv_id == "2607.01234v1"


@pytest.mark.asyncio
async def test_fetch_papers_retries_retryable_response(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, text="try again")
        return httpx.Response(200, text=ATOM_FEED)

    sleep = AsyncMock()
    monkeypatch.setattr("paperforge.services.arxiv.client.asyncio.sleep", sleep)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(
            ArxivSettings(max_retries=2, retry_backoff_seconds=1),
            client=http_client,
            monotonic=lambda: 1.0,
        )
        papers = await client.fetch_papers(max_results=1)

    assert len(papers) == 1
    assert attempts == 2
    assert sleep.await_count >= 1


@pytest.mark.asyncio
async def test_fetch_papers_rejects_non_retryable_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad query")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(ArxivSettings(max_retries=2), client=http_client)
        with pytest.raises(ArxivResponseError, match="arXiv request failed"):
            await client.fetch_papers(max_results=1)


@pytest.mark.asyncio
async def test_download_pdf_rejects_oversized_content(tmp_path: Path) -> None:
    paper = ArxivPaper(
        arxiv_id="2607.09999v1",
        title="Large paper",
        authors=["Alice"],
        abstract="Abstract",
        categories=["cs.AI"],
        published_date=datetime(2026, 7, 20, tzinfo=UTC),
        pdf_url="https://arxiv.org/pdf/2607.09999v1",
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-" + b"x" * (1024 * 1024))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = ArxivClient(
            ArxivSettings(pdf_cache_dir=tmp_path, max_retries=1, max_pdf_download_mb=1),
            client=http_client,
        )
        with pytest.raises(PdfDownloadError, match="exceeds 1 MB"):
            await client.download_pdf(paper)

    assert list(tmp_path.glob("*.part")) == []


def test_parse_atom_feed_skips_entry_with_missing_required_fields() -> None:
    malformed = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>x</id></entry></feed>"""

    assert ArxivClient.parse_atom_feed(malformed) == []
