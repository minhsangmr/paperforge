"""Tests for the Langfuse v4 adapter without a live Langfuse server."""

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any
from unittest.mock import MagicMock

from paperforge.core.config import LangfuseSettings
from paperforge.schemas.observability import FeedbackRequest
from paperforge.schemas.rag import RAGRequest
from paperforge.services.observability.langfuse import LangfuseObservability


class FakeObservation:
    def __init__(self) -> None:
        self.updates: list[dict[str, object]] = []

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)


class FakeLangfuse:
    def __init__(self) -> None:
        self.root = FakeObservation()
        self.child = FakeObservation()
        self.scores: list[dict[str, object]] = []
        self.shutdown_called = False

    @contextmanager
    def start_as_current_observation(
        self,
        **kwargs: object,
    ) -> Iterator[Any]:
        yield self.root if kwargs.get("name") == "paperforge-rag" else self.child

    def get_current_trace_id(self) -> str:
        return "a" * 32

    def create_score(self, **kwargs: object) -> None:
        self.scores.append(kwargs)

    def shutdown(self) -> None:
        self.shutdown_called = True


def _settings(**kwargs: Any) -> LangfuseSettings:
    values: dict[str, Any] = {
        "enabled": True,
        "public_key": "pk-test",
        "secret_key": "sk-test",
    }
    values.update(kwargs)
    return LangfuseSettings(**values)


def test_disabled_adapter_is_safe_noop() -> None:
    adapter = LangfuseObservability(LangfuseSettings(enabled=False))
    with adapter.trace_rag(RAGRequest(query="Question"), streaming=False) as trace:
        assert trace.trace_id is None
        with trace.observe(name="retrieval") as observation:
            observation.update(output={"hits": 0})


def test_trace_creates_root_and_nested_observation() -> None:
    client = FakeLangfuse()
    adapter = LangfuseObservability(_settings(), client=client)
    with adapter.trace_rag(RAGRequest(query="Question"), streaming=True) as trace:
        assert trace.trace_id == "a" * 32
        with trace.observe(name="retrieval") as observation:
            observation.update(output={"hits": 2})
        trace.finish(output={"answer": "complete"})
    assert client.child.updates[0]["output"] == {"hits": 2}
    assert client.root.updates[-1]["output"] == {"answer": "complete"}


def test_content_is_masked_by_default_and_optional_to_capture() -> None:
    masked = LangfuseObservability(_settings(), client=FakeLangfuse())
    masked_query = masked.content("secret question", label="query")

    assert isinstance(masked_query, dict)
    assert "query_sha256_16" in masked_query
    assert "secret question" not in str(masked_query)

    captured = LangfuseObservability(
        _settings(capture_content=True),
        client=FakeLangfuse(),
    )
    assert captured.content("question", label="query") == {
        "query": "question",
    }


def test_feedback_and_shutdown_use_sdk() -> None:
    client = FakeLangfuse()
    adapter = LangfuseObservability(_settings(), client=client)
    accepted = asyncio.run(
        adapter.submit_feedback(FeedbackRequest(trace_id="b" * 32, value=1, comment="good"))
    )
    asyncio.run(adapter.close())
    assert accepted is True
    assert client.scores[0]["trace_id"] == "b" * 32
    assert client.scores[0]["data_type"] == "NUMERIC"
    assert client.shutdown_called is True


def test_feedback_failure_is_non_fatal() -> None:
    client = MagicMock()
    client.create_score.side_effect = RuntimeError("offline")
    adapter = LangfuseObservability(_settings(), client=client)
    accepted = asyncio.run(adapter.submit_feedback(FeedbackRequest(trace_id="c" * 32, value=0)))
    assert accepted is False
