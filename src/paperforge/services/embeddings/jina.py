"""Async Jina embedding client with batching, retry, and dimension validation."""

import asyncio
import math
from collections.abc import Awaitable, Callable, Sequence

import httpx

from paperforge.core.config import EmbeddingSettings
from paperforge.exceptions import EmbeddingResponseError, EmbeddingUnavailableError

Sleep = Callable[[float], Awaitable[None]]


class JinaEmbeddingsClient:
    """Generate retrieval passage/query vectors using the configured Jina model."""

    def __init__(
        self,
        settings: EmbeddingSettings,
        client: httpx.AsyncClient | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=settings.timeout_seconds)
        self._sleep = sleep

    @property
    def available(self) -> bool:
        """Return whether external embedding calls are configured."""

        return self.settings.enabled and self.settings.api_key is not None

    async def embed_passages(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed chunk text using the retrieval-passage adapter."""

        return await self._embed(texts, task="retrieval.passage")

    async def embed_query(self, query: str) -> list[float]:
        """Embed one user query using the retrieval-query adapter."""

        vectors = await self._embed([query], task="retrieval.query")
        return vectors[0]

    async def _embed(self, texts: Sequence[str], *, task: str) -> list[list[float]]:
        if not texts:
            return []
        if not self.available:
            raise EmbeddingUnavailableError(
                "Jina embeddings are disabled or PAPERFORGE_EMBEDDINGS__API_KEY is missing"
            )

        normalized = [self._normalize_text(text) for text in texts]
        vectors: list[list[float]] = []
        for start in range(0, len(normalized), self.settings.batch_size):
            batch = normalized[start : start + self.settings.batch_size]
            vectors.extend(await self._request_batch(batch, task=task))
        return vectors

    async def _request_batch(self, texts: list[str], *, task: str) -> list[list[float]]:
        api_key = self.settings.api_key
        if api_key is None:  # pragma: no cover - guarded by available
            raise EmbeddingUnavailableError("Jina API key is missing")
        payload = {
            "model": self.settings.model,
            "task": task,
            "dimensions": self.settings.dimensions,
            "embedding_type": "float",
            "normalized": True,
            "truncate": True,
            "input": texts,
        }
        headers = {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        response: httpx.Response | None = None
        for attempt in range(self.settings.max_retries):
            try:
                response = await self._client.post(
                    self.settings.base_url,
                    headers=headers,
                    json=payload,
                )
            except httpx.TimeoutException as exc:
                if attempt + 1 >= self.settings.max_retries:
                    raise EmbeddingResponseError("Jina embedding request timed out") from exc
                await self._sleep(self.settings.retry_backoff_seconds * (2**attempt))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                if attempt + 1 >= self.settings.max_retries:
                    break
                retry_after = response.headers.get("Retry-After")
                delay = (
                    float(retry_after)
                    if retry_after is not None and retry_after.replace(".", "", 1).isdigit()
                    else self.settings.retry_backoff_seconds * (2**attempt)
                )
                await self._sleep(delay)
                continue
            break

        if response is None:  # pragma: no cover - defensive
            raise EmbeddingResponseError("Jina embedding request did not return a response")
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise EmbeddingResponseError(
                f"Jina embedding request failed with HTTP {response.status_code}"
            ) from exc

        try:
            payload_data = response.json()
            raw_items = payload_data["data"]
            ordered = sorted(raw_items, key=lambda item: int(item.get("index", 0)))
            vectors = [[float(value) for value in item["embedding"]] for item in ordered]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingResponseError("Jina returned an invalid embedding response") from exc
        if len(vectors) != len(texts):
            raise EmbeddingResponseError(
                f"Jina returned {len(vectors)} vectors for {len(texts)} inputs"
            )
        for vector in vectors:
            if len(vector) != self.settings.dimensions:
                raise EmbeddingResponseError(
                    f"Jina returned dimension {len(vector)}; expected {self.settings.dimensions}"
                )
            if not all(math.isfinite(value) for value in vector):
                raise EmbeddingResponseError("Jina returned a non-finite vector value")
        return vectors

    def _normalize_text(self, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("embedding input cannot be blank")
        return normalized[: self.settings.max_input_characters]

    async def close(self) -> None:
        """Close a client created by this adapter."""

        if self._owns_client:
            await self._client.aclose()
