"""Unit tests for the async Jina embedding adapter."""

import json
from typing import Any, cast

import httpx
import pytest
from pydantic import SecretStr

from paperforge.core.config import EmbeddingSettings
from paperforge.exceptions import EmbeddingResponseError, EmbeddingUnavailableError
from paperforge.services.embeddings.jina import JinaEmbeddingsClient


def _settings(**overrides: object) -> EmbeddingSettings:
    values: dict[str, object] = {
        "api_key": SecretStr("secret"),
        "dimensions": 3,
        "batch_size": 2,
        "max_retries": 2,
        "retry_backoff_seconds": 0.01,
    }
    values.update(overrides)
    return EmbeddingSettings.model_validate(values)


@pytest.mark.asyncio
async def test_jina_uses_task_specific_payloads_and_preserves_order() -> None:
    requests: list[dict[str, Any]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payload = cast(dict[str, Any], json.loads(request.content))
        requests.append(payload)
        inputs = cast(list[str], payload["input"])
        data = [
            {"index": index, "embedding": [float(index), 1.0, 2.0]}
            for index, _ in enumerate(inputs)
        ]
        return httpx.Response(200, json={"data": list(reversed(data))})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = JinaEmbeddingsClient(_settings(), client=client)
    passages = await adapter.embed_passages(["a", "b", "c"])
    query = await adapter.embed_query("question")
    assert len(passages) == 3
    assert passages[0] == [0.0, 1.0, 2.0]
    assert query == [0.0, 1.0, 2.0]
    assert requests[0]["task"] == "retrieval.passage"
    assert requests[0]["normalized"] is True
    assert requests[0]["truncate"] is True
    assert requests[-1]["task"] == "retrieval.query"
    await client.aclose()


@pytest.mark.asyncio
async def test_jina_retries_429() -> None:
    attempts = 0
    sleeps: list[float] = []

    async def handler(_: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "0.2"})
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2, 3]}]})

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = JinaEmbeddingsClient(_settings(), client=client, sleep=sleep)
    assert await adapter.embed_query("q") == [1.0, 2.0, 3.0]
    assert attempts == 2
    assert sleeps == [0.2]
    await client.aclose()


@pytest.mark.asyncio
async def test_jina_rejects_missing_key_and_invalid_dimension() -> None:
    unavailable = JinaEmbeddingsClient(EmbeddingSettings(api_key=None))
    with pytest.raises(EmbeddingUnavailableError):
        await unavailable.embed_query("q")
    await unavailable.close()

    async def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1, 2]}]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = JinaEmbeddingsClient(_settings(), client=client)
    with pytest.raises(EmbeddingResponseError, match="dimension"):
        await adapter.embed_query("q")
    with pytest.raises(ValueError, match="blank"):
        await adapter.embed_query("  ")
    await client.aclose()
