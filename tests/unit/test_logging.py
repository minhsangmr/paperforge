"""Tests for structured logging."""

import json
import logging

from paperforge.core.config import Settings
from paperforge.core.logging import ConsoleFormatter, JsonFormatter, configure_logging
from paperforge.core.request_context import reset_request_id, set_request_id


def test_json_formatter_includes_context_and_extra_fields() -> None:
    token = set_request_id("request-123")
    try:
        record = logging.LogRecord(
            name="paperforge.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.dependency = "postgresql"
        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["message"] == "hello"
    assert payload["request_id"] == "request-123"
    assert payload["dependency"] == "postgresql"


def test_console_formatter_and_configuration() -> None:
    settings = Settings(log_format="console", log_level="WARNING")
    configure_logging(settings)

    record = logging.LogRecord("test", logging.WARNING, __file__, 1, "warning", (), None)

    assert "warning" in ConsoleFormatter().format(record)
    assert logging.getLogger().level == logging.WARNING
