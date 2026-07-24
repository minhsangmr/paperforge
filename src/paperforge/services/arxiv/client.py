"""Rate-limited arXiv Atom client and PDF cache."""

import asyncio
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

import httpx

from paperforge.core.config import ArxivSettings
from paperforge.exceptions import (
    ArxivParseError,
    ArxivResponseError,
    ArxivTimeoutError,
    PdfDownloadError,
)
from paperforge.schemas.papers import ArxivPaper

logger = logging.getLogger(__name__)

_ATOM_NAMESPACES: Final[dict[str, str]] = {
    "atom": "http://www.w3.org/2005/Atom",
}
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class PdfDownload:
    """A validated PDF path and whether it came from local cache."""

    path: Path
    cache_hit: bool


class ArxivClient:
    """Fetch metadata and PDFs while respecting arXiv request etiquette."""

    def __init__(
        self,
        settings: ArxivSettings,
        client: httpx.AsyncClient | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = client or httpx.AsyncClient(
            timeout=settings.request_timeout_seconds,
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._monotonic = monotonic
        self._request_lock = asyncio.Lock()
        self._last_request_at: float | None = None

    @property
    def pdf_cache_dir(self) -> Path:
        """Create and return the Linux-container cache directory."""

        self._settings.pdf_cache_dir.mkdir(parents=True, exist_ok=True)
        return self._settings.pdf_cache_dir

    async def close(self) -> None:
        """Close the internally-owned HTTP client."""

        if self._owns_client:
            await self._client.aclose()

    async def fetch_papers(
        self,
        *,
        max_results: int | None = None,
        start: int = 0,
        from_date: str | None = None,
        to_date: str | None = None,
        sort_by: str = "submittedDate",
        sort_order: str = "descending",
    ) -> list[ArxivPaper]:
        """Fetch one page of papers for the configured arXiv category."""

        limit = min(max_results or self._settings.max_results, 2000)
        query = f"cat:{self._settings.category}"

        if from_date is not None or to_date is not None:
            lower = f"{from_date}0000" if from_date is not None else "*"
            upper = f"{to_date}2359" if to_date is not None else "*"
            query = f"{query} AND submittedDate:[{lower} TO {upper}]"

        params: dict[str, str | int | float | bool | None] = {
            "search_query": query,
            "start": start,
            "max_results": limit,
            "sortBy": sort_by,
            "sortOrder": sort_order,
        }

        response = await self._get(
            self._settings.base_url,
            params=params,
        )
        return self.parse_atom_feed(response.text)

    async def fetch_paper_by_id(self, arxiv_id: str) -> ArxivPaper | None:
        """Fetch one paper by identifier."""

        response = await self._get(
            self._settings.base_url,
            params={"id_list": arxiv_id, "max_results": 1},
        )
        papers = self.parse_atom_feed(response.text)
        return papers[0] if papers else None

    async def download_pdf(
        self,
        paper: ArxivPaper,
        *,
        force: bool = False,
    ) -> PdfDownload:
        """Download a PDF atomically or return a previously validated cache file."""

        if not paper.pdf_url:
            raise PdfDownloadError(f"paper {paper.arxiv_id} has no PDF URL")

        destination = self._pdf_path(paper.arxiv_id)
        if destination.exists() and not force:
            self._validate_pdf(destination)
            return PdfDownload(path=destination, cache_hit=True)

        partial = destination.with_suffix(".pdf.part")
        partial.unlink(missing_ok=True)
        max_bytes = self._settings.max_pdf_download_mb * 1024 * 1024

        for attempt in range(1, self._settings.max_retries + 1):
            try:
                async with self._request_lock:
                    await self._wait_for_rate_limit()
                    async with self._client.stream(
                        "GET",
                        paper.pdf_url,
                        headers={"User-Agent": self._settings.user_agent},
                    ) as response:
                        self._last_request_at = self._monotonic()
                        response.raise_for_status()
                        size = 0
                        with partial.open("wb") as output:
                            async for chunk in response.aiter_bytes():
                                size += len(chunk)
                                if size > max_bytes:
                                    raise PdfDownloadError(
                                        f"PDF exceeds {self._settings.max_pdf_download_mb} MB"
                                    )
                                output.write(chunk)
                self._validate_pdf(partial)
                partial.replace(destination)
                return PdfDownload(path=destination, cache_hit=False)
            except PdfDownloadError:
                partial.unlink(missing_ok=True)
                raise
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                partial.unlink(missing_ok=True)
                if attempt == self._settings.max_retries:
                    raise PdfDownloadError(
                        f"failed to download {paper.arxiv_id} after {attempt} attempts: {exc}"
                    ) from exc
                await asyncio.sleep(self._settings.retry_backoff_seconds * attempt)

        raise PdfDownloadError(f"failed to download {paper.arxiv_id}")

    async def _get(
        self,
        url: str,
        *,
        params: dict[str, str | int | float | bool | None],
    ) -> httpx.Response:
        for attempt in range(1, self._settings.max_retries + 1):
            try:
                async with self._request_lock:
                    await self._wait_for_rate_limit()
                    response = await self._client.get(
                        url,
                        params=params,
                        headers={"User-Agent": self._settings.user_agent},
                    )
                    self._last_request_at = self._monotonic()

                response.raise_for_status()
                return response

            except httpx.TimeoutException as exc:
                if attempt == self._settings.max_retries:
                    raise ArxivTimeoutError(f"arXiv request timed out: {exc}") from exc

            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                retryable = not isinstance(exc, httpx.HTTPStatusError) or (
                    exc.response.status_code == 429 or exc.response.status_code >= 500
                )

                if not retryable or attempt == self._settings.max_retries:
                    raise ArxivResponseError(f"arXiv request failed: {exc}") from exc

            await asyncio.sleep(self._settings.retry_backoff_seconds * attempt)

        raise ArxivResponseError("arXiv request failed without a response")

    async def _wait_for_rate_limit(self) -> None:
        if self._last_request_at is None:
            return
        elapsed = self._monotonic() - self._last_request_at
        remaining = self._settings.rate_limit_seconds - elapsed
        if remaining > 0:
            await asyncio.sleep(remaining)

    def _pdf_path(self, arxiv_id: str) -> Path:
        safe_id = re.sub(r"[^A-Za-z0-9._-]+", "_", arxiv_id)
        return self.pdf_cache_dir / f"{safe_id}.pdf"

    @staticmethod
    def _validate_pdf(path: Path) -> None:
        if not path.is_file() or path.stat().st_size < 5:
            raise PdfDownloadError(f"invalid or empty PDF cache file: {path}")
        with path.open("rb") as handle:
            if handle.read(5) != b"%PDF-":
                raise PdfDownloadError(f"downloaded file is not a PDF: {path}")

    @classmethod
    def parse_atom_feed(cls, xml_data: str) -> list[ArxivPaper]:
        """Parse an arXiv Atom feed into normalized immutable schemas."""

        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as exc:
            raise ArxivParseError(f"invalid arXiv Atom XML: {exc}") from exc

        papers: list[ArxivPaper] = []
        for entry in root.findall("atom:entry", _ATOM_NAMESPACES):
            try:
                arxiv_id = cls._text(entry, "atom:id").rsplit("/", 1)[-1]
                pdf_url = cls._pdf_url(entry)
                published = datetime.fromisoformat(
                    cls._text(entry, "atom:published").replace("Z", "+00:00")
                )
                paper = ArxivPaper(
                    arxiv_id=arxiv_id,
                    title=cls._text(entry, "atom:title", normalize=True),
                    authors=[
                        cls._text(author, "atom:name", normalize=True)
                        for author in entry.findall("atom:author", _ATOM_NAMESPACES)
                    ],
                    abstract=cls._text(entry, "atom:summary", normalize=True),
                    categories=[
                        term
                        for category in entry.findall("atom:category", _ATOM_NAMESPACES)
                        if (term := category.get("term")) is not None
                    ],
                    published_date=published,
                    pdf_url=pdf_url,
                )
            except (ValueError, KeyError) as exc:
                logger.warning("arxiv.entry_skipped", extra={"reason": str(exc)})
                continue
            papers.append(paper)
        return papers

    @staticmethod
    def _text(element: ET.Element, path: str, *, normalize: bool = False) -> str:
        child = element.find(path, _ATOM_NAMESPACES)
        if child is None or child.text is None:
            raise ValueError(f"missing Atom field: {path}")
        value = child.text.strip()
        return _WHITESPACE.sub(" ", value) if normalize else value

    @staticmethod
    def _pdf_url(entry: ET.Element) -> str:
        for link in entry.findall("atom:link", _ATOM_NAMESPACES):
            if link.get("type") == "application/pdf":
                return link.get("href", "").replace("http://arxiv.org/", "https://arxiv.org/")
        raise ValueError("missing PDF link")
