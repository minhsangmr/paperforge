"""Validation tests for Week 5 RAG contracts."""

import pytest
from pydantic import ValidationError

from paperforge.schemas.rag import OllamaUsage, RAGRequest


def test_request_normalizes_query_model_and_categories() -> None:
    request = RAGRequest(
        query="  What is RAG?  ",
        model=" llama3.2:1b ",
        categories=[" cs.AI ", "", "cs.AI", "cs.IR"],
    )

    assert request.query == "What is RAG?"
    assert request.model == "llama3.2:1b"
    assert request.categories == ["cs.AI", "cs.IR"]


@pytest.mark.parametrize(
    "payload",
    [
        {"query": "   "},
        {"query": "Question", "model": "  "},
        {"query": "Question", "top_k": 0},
    ],
)
def test_request_rejects_invalid_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        RAGRequest.model_validate(payload)


def test_usage_derives_total_tokens() -> None:
    usage = OllamaUsage(prompt_tokens=7, completion_tokens=5)
    assert usage.total_tokens == 12
