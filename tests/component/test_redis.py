"""Redis component tests against Docker Compose."""

from uuid import uuid4

import pytest

from paperforge.core.config import get_settings
from paperforge.infrastructure.redis import RedisClient

pytestmark = pytest.mark.component


def test_redis_round_trip_and_ttl() -> None:
    client = RedisClient(get_settings().redis)
    key = f"paperforge:component:{uuid4()}"
    try:
        assert client.ping() is True
        assert client.set(key, "value", ttl_seconds=30) is True
        assert client.get(key) == "value"
        assert 0 < client.ttl(key) <= 30
    finally:
        client.delete(key)
        client.close()
