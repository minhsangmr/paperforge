"""Tests for Paperforge settings."""

from paperforge.core.config import Settings


def test_settings_have_safe_development_defaults() -> None:
    settings = Settings()

    assert settings.environment == "development"
    assert settings.port == 8000
    assert settings.reload is True
