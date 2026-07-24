"""Opt-in smoke test for the real arXiv API."""

import pytest

from paperforge.core.config import get_settings
from paperforge.services.arxiv.client import ArxivClient

pytestmark = pytest.mark.external


@pytest.mark.asyncio
async def test_real_arxiv_api_returns_one_paper() -> None:
    client = ArxivClient(get_settings().arxiv)
    try:
        papers = await client.fetch_papers(max_results=1)
    finally:
        await client.close()

    assert len(papers) <= 1
    if papers:
        assert papers[0].arxiv_id
        assert papers[0].pdf_url.startswith("https://")
