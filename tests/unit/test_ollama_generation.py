"""Tests for Ollama generation and NDJSON streaming."""

import asyncio

import httpx

from paperforge.core.config import OllamaSettings
from paperforge.services.ollama.client import OllamaClient


def test_generate_normalizes_answer_and_usage() -> None:
    async def run() -> tuple[str, int, float | None]:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/api/generate"
            return httpx.Response(
                200,
                request=request,
                json={
                    "response": " Grounded answer [S1] ",
                    "prompt_eval_count": 10,
                    "eval_count": 4,
                    "total_duration": 2_500_000,
                },
            )

        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http:
            client = OllamaClient(OllamaSettings(), client=http)
            answer, usage = await client.generate(prompt="prompt", model="llama3.2:1b")
            return answer, usage.total_tokens, usage.latency_ms

    answer, total_tokens, latency_ms = asyncio.run(run())
    assert answer == "Grounded answer [S1]"
    assert total_tokens == 14
    assert latency_ms == 2.5


def test_stream_parses_ndjson_in_order() -> None:
    async def run() -> list[dict[str, object]]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                content=(
                    b'{"response":"Grounded ","done":false}\n'
                    b'{"response":"answer","done":true,"eval_count":2}\n'
                ),
            )
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http:
            client = OllamaClient(OllamaSettings(), client=http)
            return [item async for item in client.generate_stream(prompt="p", model="m")]

    chunks = asyncio.run(run())
    assert [chunk["response"] for chunk in chunks] == ["Grounded ", "answer"]
    assert chunks[-1]["done"] is True


def test_list_models_returns_names() -> None:
    async def run() -> list[str]:
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                request=request,
                json={"models": [{"name": "llama3.2:1b"}, {"name": "qwen2.5:3b"}]},
            )
        )
        async with httpx.AsyncClient(transport=transport, base_url="http://ollama") as http:
            client = OllamaClient(OllamaSettings(), client=http)
            return await client.list_models()

    assert asyncio.run(run()) == ["llama3.2:1b", "qwen2.5:3b"]
