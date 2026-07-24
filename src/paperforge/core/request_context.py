"""Request-scoped context values."""

from contextvars import ContextVar, Token

_request_id: ContextVar[str] = ContextVar("paperforge_request_id", default="-")


def get_request_id() -> str:
    """Return the current request ID or a placeholder outside requests."""

    return _request_id.get()


def set_request_id(value: str) -> Token[str]:
    """Set a request ID and return the reset token."""

    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    """Restore the previous request context."""

    _request_id.reset(token)
