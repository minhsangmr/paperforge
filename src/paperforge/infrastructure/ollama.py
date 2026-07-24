"""Minimal Ollama health adapter."""

import httpx

from paperforge.core.config import OllamaSettings


class OllamaClient:
    """Check Ollama availability without implementing generation yet."""

    def __init__(
        self,
        settings: OllamaSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.url,
            timeout=settings.timeout_seconds,
        )

    async def ping(self) -> bool:
        """Return true when Ollama exposes its tags endpoint."""

        response = await self._client.get("/api/tags")
        return response.is_success

    async def close(self) -> None:
        """Close only clients created by this adapter."""

        if self._owns_client:
            await self._client.aclose()
