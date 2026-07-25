"""Langfuse v4 adapter with safe no-op behavior when disabled."""

import asyncio
import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx

from paperforge.core.config import LangfuseSettings
from paperforge.schemas.observability import FeedbackRequest
from paperforge.schemas.rag import RAGRequest

logger = logging.getLogger(__name__)


class ObservationHandle:
    """Small wrapper that hides the external SDK from application services."""

    def __init__(self, observation: Any | None) -> None:
        self._observation = observation

    def update(
        self,
        *,
        output: object | None = None,
        metadata: dict[str, object] | None = None,
        usage_details: dict[str, int] | None = None,
        level: str | None = None,
        status_message: str | None = None,
    ) -> None:
        if self._observation is None:
            return
        kwargs: dict[str, object] = {}
        if output is not None:
            kwargs["output"] = output
        if metadata is not None:
            kwargs["metadata"] = metadata
        if usage_details is not None:
            kwargs["usage_details"] = usage_details
        if level is not None:
            kwargs["level"] = level
        if status_message is not None:
            kwargs["status_message"] = status_message
        try:
            self._observation.update(**kwargs)
        except Exception:
            logger.exception("langfuse.observation_update_failed")


class TraceSession:
    """Request-scoped root trace and nested observation factory."""

    def __init__(
        self,
        *,
        client: Any | None,
        root: Any | None,
        trace_id: str | None,
        capture_content: bool,
    ) -> None:
        self._client = client
        self._root = ObservationHandle(root)
        self.trace_id = trace_id
        self.capture_content = capture_content

    @contextmanager
    def observe(
        self,
        *,
        name: str,
        as_type: str = "span",
        input_data: object | None = None,
        metadata: dict[str, object] | None = None,
        model: str | None = None,
        model_parameters: dict[str, object] | None = None,
    ) -> Iterator[ObservationHandle]:
        """Create a nested observation or a no-op handle."""

        if self._client is None:
            yield ObservationHandle(None)
            return
        kwargs: dict[str, object] = {
            "name": name,
            "as_type": as_type,
            "input": input_data,
            "metadata": metadata,
        }
        if model is not None:
            kwargs["model"] = model
        if model_parameters is not None:
            kwargs["model_parameters"] = model_parameters
        try:
            manager = self._client.start_as_current_observation(**kwargs)
        except Exception:
            logger.exception("langfuse.observation_failed", extra={"observation": name})
            yield ObservationHandle(None)
            return
        with manager as observation:
            yield ObservationHandle(observation)

    def finish(
        self,
        *,
        output: dict[str, object],
        metadata: dict[str, object] | None = None,
    ) -> None:
        self._root.update(output=output, metadata=metadata)

    def mark_error(self, exc: BaseException) -> None:
        self._root.update(
            level="ERROR",
            status_message=str(exc),
            metadata={"error_type": type(exc).__name__},
        )


class LangfuseObservability:
    """Optional Langfuse adapter using the current OpenTelemetry-based Python SDK."""

    def __init__(self, settings: LangfuseSettings, client: Any | None = None) -> None:
        self.settings = settings
        self._client = client
        if client is None and settings.enabled and settings.configured:
            try:
                from langfuse import Langfuse

                assert settings.public_key is not None
                assert settings.secret_key is not None
                self._client = Langfuse(
                    public_key=settings.public_key.get_secret_value(),
                    secret_key=settings.secret_key.get_secret_value(),
                    base_url=settings.base_url,
                    timeout=settings.timeout_seconds,
                    tracing_enabled=True,
                    flush_at=settings.flush_at,
                    flush_interval=settings.flush_interval_seconds,
                    environment=settings.tracing_environment,
                    release=settings.release,
                    sample_rate=settings.sample_rate,
                )
            except Exception:
                logger.exception("langfuse.initialization_failed")
                self._client = None

    @property
    def enabled(self) -> bool:
        return self.settings.enabled and self._client is not None

    @contextmanager
    def trace_rag(self, request: RAGRequest, *, streaming: bool) -> Iterator[TraceSession]:
        """Create one root RAG trace with nested retrieval/cache/generation observations."""

        if not self.enabled:
            yield TraceSession(
                client=None,
                root=None,
                trace_id=None,
                capture_content=self.settings.capture_content,
            )
            return

        assert self._client is not None
        input_data = self._content_or_summary(
            request.query,
            label="query",
        )
        metadata: dict[str, object] = {
            "streaming": streaming,
            "top_k": request.top_k,
            "use_hybrid": request.use_hybrid,
            "categories": request.categories,
        }
        if request.user_id is not None:
            metadata["user_id"] = request.user_id
        if request.session_id is not None:
            metadata["session_id"] = request.session_id

        try:
            with self._client.start_as_current_observation(
                name="paperforge-rag",
                as_type="chain",
                input=input_data,
                metadata=metadata,
                version=self.settings.release,
            ) as root:
                trace_id = self._client.get_current_trace_id()
                session = TraceSession(
                    client=self._client,
                    root=root,
                    trace_id=trace_id,
                    capture_content=self.settings.capture_content,
                )
                try:
                    yield session
                except BaseException as exc:
                    session.mark_error(exc)
                    raise
        except BaseException:
            raise

    async def ping(self) -> bool:
        """Check the self-hosted Langfuse web health endpoint."""

        if not self.settings.enabled or not self.settings.configured:
            return False
        try:
            async with httpx.AsyncClient(timeout=self.settings.timeout_seconds) as client:
                response = await client.get(
                    f"{self.settings.base_url.rstrip('/')}/api/public/health"
                )
            return response.is_success
        except httpx.HTTPError:
            return False

    async def submit_feedback(self, request: FeedbackRequest) -> bool:
        """Queue a numeric score for one trace."""

        if not self.enabled:
            return False
        assert self._client is not None
        try:
            await asyncio.to_thread(
                self._client.create_score,
                trace_id=request.trace_id,
                name=self.settings.score_name,
                value=float(request.value),
                data_type="NUMERIC",
                comment=request.comment,
                metadata={"source": "paperforge-api"},
            )
            return True
        except Exception:
            logger.exception("langfuse.feedback_failed", extra={"trace_id": request.trace_id})
            return False

    async def close(self) -> None:
        """Flush and shut down SDK background workers."""

        if self._client is None:
            return
        try:
            await asyncio.to_thread(self._client.shutdown)
        except Exception:
            logger.exception("langfuse.shutdown_failed")

    def content(self, value: str, *, label: str) -> object:
        """Return raw content only when explicitly enabled."""

        return self._content_or_summary(value, label=label)

    def _content_or_summary(self, value: str, *, label: str) -> object:
        if self.settings.capture_content:
            return {label: value}
        digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]
        return {f"{label}_length": len(value), f"{label}_sha256_16": digest}
