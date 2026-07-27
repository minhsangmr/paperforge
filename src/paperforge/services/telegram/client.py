"""Async HTTP client used by the separate Telegram polling process."""

import httpx

from paperforge.core.config import TelegramSettings
from paperforge.schemas.agentic import AgenticRAGRequest, AgenticRAGResponse


class PaperforgeAPIClient:
    """Call Paperforge API endpoints without duplicating RAG infrastructure in the bot."""

    def __init__(
        self,
        settings: TelegramSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.api_base_url.rstrip("/"),
            timeout=httpx.Timeout(settings.request_timeout_seconds),
        )

    async def ask(
        self,
        query: str,
        *,
        user_id: str,
        session_id: str,
    ) -> AgenticRAGResponse:
        request = AgenticRAGRequest(
            query=query,
            user_id=user_id,
            session_id=session_id,
        )
        response = await self._client.post("/agentic-ask", json=request.model_dump(mode="json"))
        response.raise_for_status()
        return AgenticRAGResponse.model_validate(response.json())

    async def healthy(self) -> bool:
        try:
            response = await self._client.get("/health/live", timeout=5)
            return response.is_success
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
