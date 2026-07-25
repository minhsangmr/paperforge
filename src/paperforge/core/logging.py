"""Structured logging configuration."""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from paperforge.core.config import Settings
from paperforge.core.request_context import get_request_id

_STANDARD_FIELDS = set(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    """Serialize log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id(),
        }

        for key, value in record.__dict__.items():
            if key not in _STANDARD_FIELDS and not key.startswith("_"):
                payload[key] = value

        raw_exc_info: Any = record.exc_info
        if raw_exc_info:
            exc_info = sys.exc_info() if raw_exc_info is True else raw_exc_info
            if isinstance(exc_info, tuple) and exc_info[0] is not None:
                payload["exception"] = self.formatException(exc_info)

        return json.dumps(payload, default=str, ensure_ascii=False)


class ConsoleFormatter(logging.Formatter):
    """Human-readable formatter for local debugging."""

    def format(self, record: logging.LogRecord) -> str:
        prefix = f"{record.levelname:<8} [{get_request_id()}] {record.name}"
        return f"{prefix}: {record.getMessage()}"


def configure_logging(settings: Settings) -> None:
    """Configure root and server loggers once per application startup."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter() if settings.log_format == "json" else ConsoleFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(settings.log_level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
