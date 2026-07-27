import httpx
import pytest

from paperforge.core.config import TelegramSettings
from paperforge.schemas.agentic import AgenticRAGResponse, GuardrailResult
from paperforge.services.telegram.bot import format_agentic_response, split_message
from paperforge.services.telegram.client import PaperforgeAPIClient


def response() -> AgenticRAGResponse:
    return AgenticRAGResponse(
        query="RAG",
        answer="Answer",
        sources=[],
        chunks_used=0,
        search_mode="bm25",
        model="llama3.2:1b",
        reasoning_steps=[],
        retrieval_attempts=1,
        guardrail=GuardrailResult(score=90, reason="research", accepted=True),
        status="completed",
    )


def test_split_message_respects_limit() -> None:
    parts = split_message("word " * 100, 80)
    assert len(parts) > 1
    assert all(len(part) <= 80 for part in parts)


def test_format_agentic_response_has_status() -> None:
    assert "Status: completed" in format_agentic_response(response())


@pytest.mark.asyncio
async def test_telegram_api_client_calls_agentic_endpoint() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/agentic-ask"
        return httpx.Response(200, json=response().model_dump(mode="json"))

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="http://api:8000/api/v1"
    )
    api = PaperforgeAPIClient(TelegramSettings(), client)
    result = await api.ask("RAG", user_id="telegram:1", session_id="chat:1")
    assert result.answer == "Answer"


@pytest.mark.asyncio
async def test_telegram_api_health_and_close() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/health/live"
        return httpx.Response(200)

    api = PaperforgeAPIClient(
        TelegramSettings(),
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://api:8000/api/v1",
        ),
    )
    assert await api.healthy() is True
    await api.close()


@pytest.mark.asyncio
async def test_telegram_api_health_failure() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("offline", request=request)

    api = PaperforgeAPIClient(
        TelegramSettings(),
        httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="http://api:8000/api/v1",
        ),
    )
    assert await api.healthy() is False
