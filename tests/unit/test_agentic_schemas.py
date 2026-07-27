import pytest
from pydantic import SecretStr, ValidationError

from paperforge.core.config import AgenticSettings, TelegramSettings
from paperforge.schemas.agentic import AgenticRAGRequest


def test_agentic_request_normalizes_categories() -> None:
    request = AgenticRAGRequest(query="  What is RAG? ", categories=["cs.AI", "", "cs.AI"])
    assert request.query == "What is RAG?"
    assert request.categories == ["cs.AI"]


def test_agentic_request_limits_attempts() -> None:
    with pytest.raises(ValidationError):
        AgenticRAGRequest(query="RAG", max_retrieval_attempts=6)


def test_agentic_settings_validate_top_k() -> None:
    with pytest.raises(ValidationError):
        AgenticSettings(default_top_k=5, max_top_k=3)


def test_blank_telegram_token_is_not_configured() -> None:
    settings = TelegramSettings(enabled=True, bot_token=SecretStr(""))
    assert settings.bot_token is None
    assert settings.configured is False
