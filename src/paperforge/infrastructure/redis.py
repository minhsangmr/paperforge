"""Redis connectivity adapter."""

from typing import Any, cast

from redis import Redis

from paperforge.core.config import RedisSettings


class RedisClient:
    """Provide cache primitives without leaking redis-py across the app."""

    def __init__(self, settings: RedisSettings, client: Any | None = None) -> None:
        self.settings = settings
        self._client: Any = client or Redis.from_url(
            settings.url,
            decode_responses=True,
            socket_connect_timeout=settings.connect_timeout_seconds,
            socket_timeout=settings.socket_timeout_seconds,
        )

    def ping(self) -> bool:
        """Return true when Redis responds to PING."""

        return bool(self._client.ping())

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> bool:
        """Store a string using the configured default TTL."""

        ttl = ttl_seconds or self.settings.default_ttl_seconds
        return bool(self._client.set(name=key, value=value, ex=ttl))

    def get(self, key: str) -> str | None:
        """Read a cached string value."""

        return cast(str | None, self._client.get(key))

    def ttl(self, key: str) -> int:
        """Return remaining TTL for diagnostics and tests."""

        return int(self._client.ttl(key))

    def increment(self, key: str, amount: int = 1) -> int:
        """Increment one integer counter."""

        return int(self._client.incrby(key, amount))

    def get_many(self, keys: list[str]) -> list[str | None]:
        """Read several string keys in one Redis round trip."""

        values = self._client.mget(keys)
        return [cast(str | None, value) for value in values]

    def delete(self, key: str) -> int:
        """Delete a cache key."""

        return int(self._client.delete(key))

    def close(self) -> None:
        """Close the underlying Redis client."""

        self._client.close()
