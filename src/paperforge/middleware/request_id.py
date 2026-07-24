"""Request ID propagation and access logging middleware."""

import logging
from time import perf_counter
from typing import Final
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from paperforge.core.request_context import reset_request_id, set_request_id

logger = logging.getLogger(__name__)
REQUEST_ID_HEADER: Final[bytes] = b"x-request-id"


def _request_id_from_scope(scope: Scope) -> str:
    for name, value in scope.get("headers", []):
        if name.lower() == REQUEST_ID_HEADER:
            candidate = value.decode("latin-1").strip()
            if (
                isinstance(candidate, str)
                and candidate
                and len(candidate) <= 128
                and candidate.isprintable()
            ):
                return candidate
    return str(uuid4())


class RequestIDMiddleware:
    """Attach a request ID and emit one structured completion log."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _request_id_from_scope(scope)
        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        token = set_request_id(request_id)
        started_at = perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER, request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception:
            logger.exception(
                "request.failed",
                extra={
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
            raise
        else:
            logger.info(
                "request.completed",
                extra={
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status_code": status_code,
                    "duration_ms": round((perf_counter() - started_at) * 1000, 2),
                },
            )
        finally:
            reset_request_id(token)
