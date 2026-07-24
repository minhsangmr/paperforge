"""Tests for the minimal Ollama health adapter."""

import asyncio

import httpx
import pytest

from paperforge.core.config import OllamaSettings
from paperforge.infrastructure.ollama import OllamaClient


@pytest.mark.parametrize(("status_code", "expected"), [(200, True), (503, False)])
def test_ollama_ping(status_code: int, expected: bool) -> None:
    async def run() -> bool:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(status_code, request=request)
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http_client:
            adapter = OllamaClient(OllamaSettings(), client=http_client)
            result = await adapter.ping()
            await adapter.close()
            return result

    assert asyncio.run(run()) is expected
