"""Tests for Redis adapter primitives."""

from unittest.mock import MagicMock

from paperforge.core.config import RedisSettings
from paperforge.infrastructure.redis import RedisClient


def test_redis_adapter_uses_ttl_and_closes() -> None:
    raw_client = MagicMock()
    raw_client.ping.return_value = True
    raw_client.set.return_value = True
    raw_client.get.return_value = "value"
    raw_client.ttl.return_value = 30
    raw_client.delete.return_value = 1
    adapter = RedisClient(RedisSettings(default_ttl_seconds=60), client=raw_client)

    assert adapter.ping() is True
    assert adapter.set("key", "value") is True
    assert adapter.get("key") == "value"
    assert adapter.ttl("key") == 30
    assert adapter.delete("key") == 1
    adapter.close()

    raw_client.set.assert_called_once_with(name="key", value="value", ex=60)
    raw_client.close.assert_called_once_with()
