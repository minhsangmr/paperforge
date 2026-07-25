"""Async Ollama generation client with NDJSON streaming support."""

import json
from collections.abc import AsyncIterator
from typing import Any, cast

import httpx

from paperforge.core.config import OllamaSettings
from paperforge.exceptions import (
    OllamaConnectionError,
    OllamaGenerationError,
    OllamaTimeoutError,
)
from paperforge.schemas.rag import OllamaUsage


class OllamaClient:
    """Process-owned adapter for Ollama health, model discovery, and generation."""

    def __init__(
        self,
        settings: OllamaSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.url,
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )

    async def ping(self) -> bool:
        """Return true when Ollama responds to its version endpoint."""

        try:
            response = await self._client.get(
                "/api/version",
                timeout=self.settings.health_timeout_seconds,
            )
            return response.is_success
        except httpx.HTTPError:
            return False

    async def list_models(self) -> list[str]:
        """Return installed Ollama model names."""

        response = await self._request("GET", "/api/tags")
        data = cast(dict[str, Any], response.json())
        models = cast(list[dict[str, Any]], data.get("models", []))
        return [str(model.get("name", "")) for model in models if model.get("name")]

    async def generate(self, *, prompt: str, model: str) -> tuple[str, OllamaUsage]:
        """Generate one complete answer and normalize usage metadata."""

        payload = self._payload(prompt=prompt, model=model, stream=False)
        response = await self._request("POST", "/api/generate", json=payload)
        data = cast(dict[str, Any], response.json())
        answer = str(data.get("response", "")).strip()
        if not answer:
            raise OllamaGenerationError("Ollama returned an empty response")
        return answer, self._usage(data)

    async def generate_stream(
        self,
        *,
        prompt: str,
        model: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield validated NDJSON objects from Ollama's streaming endpoint."""

        payload = self._payload(prompt=prompt, model=model, stream=True)
        try:
            async with self._client.stream("POST", "/api/generate", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise OllamaGenerationError("Ollama returned malformed NDJSON") from exc
                    if not isinstance(item, dict):
                        raise OllamaGenerationError("Ollama stream item must be an object")
                    yield cast(dict[str, Any], item)
        except httpx.ConnectError as exc:
            raise OllamaConnectionError("cannot connect to Ollama") from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama generation timed out") from exc
        except httpx.HTTPStatusError as exc:
            detail = (await exc.response.aread()).decode(errors="replace")[:300]
            raise OllamaGenerationError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc

    async def close(self) -> None:
        """Close only the HTTP client created by this adapter."""

        if self._owns_client:
            await self._client.aclose()

    def _payload(self, *, prompt: str, model: str, stream: bool) -> dict[str, Any]:
        return {
            "model": model,
            "prompt": prompt,
            "stream": stream,
            "keep_alive": self.settings.keep_alive,
            "options": {
                "temperature": self.settings.temperature,
                "top_p": self.settings.top_p,
                "num_predict": self.settings.max_output_tokens,
            },
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
            return response
        except httpx.ConnectError as exc:
            raise OllamaConnectionError("cannot connect to Ollama") from exc
        except httpx.TimeoutException as exc:
            raise OllamaTimeoutError("Ollama request timed out") from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise OllamaGenerationError(
                f"Ollama returned HTTP {exc.response.status_code}: {detail}"
            ) from exc

    @staticmethod
    def _usage(data: dict[str, Any]) -> OllamaUsage:
        prompt_tokens = int(data.get("prompt_eval_count", 0) or 0)
        completion_tokens = int(data.get("eval_count", 0) or 0)
        total_duration = data.get("total_duration")
        latency_ms = (
            round(float(total_duration) / 1_000_000, 2)
            if isinstance(total_duration, (int, float))
            else None
        )
        return OllamaUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            latency_ms=latency_ms,
        )
