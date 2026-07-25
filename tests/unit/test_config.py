"""Tests for typed application settings."""

import pytest
from pydantic import ValidationError

from paperforge.core.config import (
    ChunkingSettings,
    DatabaseSettings,
    HybridSearchSettings,
    Settings,
)


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


def test_week4_settings_reject_invalid_windows_and_weights() -> None:
    with pytest.raises(ValueError, match="overlap_words"):
        ChunkingSettings(chunk_size_words=100, overlap_words=100)
    with pytest.raises(ValueError, match=r"sum to 1.0"):
        HybridSearchSettings(bm25_weight=0.8, vector_weight=0.3)


def test_blank_embedding_api_key_is_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PAPERFORGE_EMBEDDINGS__API_KEY", "")
    settings = Settings()
    assert settings.embeddings.api_key is None
