"""Tests for typed application settings."""

import pytest
from pydantic import ValidationError

from paperforge.core.config import DatabaseSettings, Settings


def test_settings_load_nested_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPERFORGE_DATABASE__POOL_SIZE", "9")
    monkeypatch.setenv("PAPERFORGE_REDIS__ENABLED", "false")
    monkeypatch.setenv("PAPERFORGE_OPENSEARCH__INDEX_NAME", "test-index")

    settings = Settings()

    assert settings.database.pool_size == 9
    assert settings.redis.enabled is False
    assert settings.opensearch.index_name == "test-index"


def test_database_settings_reject_non_postgresql_url() -> None:
    with pytest.raises(ValidationError, match="must use PostgreSQL"):
        DatabaseSettings(url="sqlite+pysqlite:///:memory:")
