"""Tests for resource construction and shutdown."""

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

from paperforge.core.config import OllamaSettings, RedisSettings, Settings
from paperforge.infrastructure.database import Database
from paperforge.infrastructure.ollama import OllamaClient
from paperforge.infrastructure.opensearch import OpenSearchClient
from paperforge.infrastructure.redis import RedisClient
from paperforge.infrastructure.resources import Infrastructure, build_infrastructure


def test_infrastructure_close_releases_every_adapter() -> None:
    database = MagicMock()
    opensearch = MagicMock()
    redis = MagicMock()
    ollama = MagicMock()
    ollama.close = AsyncMock()
    infrastructure = Infrastructure(
        database=cast(Database, database),
        opensearch=cast(OpenSearchClient, opensearch),
        redis=cast(RedisClient, redis),
        ollama=cast(OllamaClient, ollama),
    )

    asyncio.run(infrastructure.close())

    ollama.close.assert_awaited_once_with()
    redis.close.assert_called_once_with()
    opensearch.close.assert_called_once_with()
    database.close.assert_called_once_with()


def test_build_infrastructure_respects_enabled_flags() -> None:
    settings = Settings(
        redis=RedisSettings(enabled=False),
        ollama=OllamaSettings(enabled=False),
    )
    with (
        patch("paperforge.infrastructure.resources.Database") as database_class,
        patch("paperforge.infrastructure.resources.OpenSearchClient") as opensearch_class,
    ):
        infrastructure = build_infrastructure(settings)

    database_class.assert_called_once_with(settings.database)
    opensearch_class.assert_called_once_with(settings.opensearch)
    assert infrastructure.redis is None
    assert infrastructure.ollama is None
