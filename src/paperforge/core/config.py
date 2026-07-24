"""Typed application configuration."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class FrozenSettingsModel(BaseModel):
    """Immutable base for nested settings sections."""

    model_config = ConfigDict(frozen=True)


class DatabaseSettings(FrozenSettingsModel):
    """PostgreSQL connection and pool settings."""

    url: str = "postgresql+psycopg://paperforge:paperforge-local-only@postgres:5432/paperforge"
    echo: bool = False
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=5, ge=0, le=100)
    pool_timeout_seconds: int = Field(default=30, ge=1, le=300)
    connect_timeout_seconds: int = Field(default=3, ge=1, le=60)

    @model_validator(mode="after")
    def validate_postgresql_url(self) -> Self:
        """Reject accidental SQLite or host-only database URLs."""

        if not self.url.startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("database URL must use PostgreSQL")
        return self


class OpenSearchSettings(FrozenSettingsModel):
    """OpenSearch connectivity and bootstrap settings."""

    enabled: bool = True
    required: bool = True
    url: str = "http://opensearch:9200"
    index_name: str = "paperforge-papers-v1"
    timeout_seconds: float = Field(default=5.0, gt=0, le=60)


class RedisSettings(FrozenSettingsModel):
    """Redis connectivity and default cache settings."""

    enabled: bool = True
    required: bool = False
    url: str = "redis://redis:6379/0"
    connect_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    socket_timeout_seconds: float = Field(default=2.0, gt=0, le=60)
    default_ttl_seconds: int = Field(default=21600, ge=1)


class OllamaSettings(FrozenSettingsModel):
    """Ollama health adapter settings; generation is added in Week 5."""

    enabled: bool = False
    required: bool = False
    url: str = "http://ollama:11434"
    timeout_seconds: float = Field(default=3.0, gt=0, le=60)


class Settings(BaseSettings):
    """Environment-driven settings for Paperforge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PAPERFORGE_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
        frozen=True,
    )

    environment: Literal["development", "test", "production"] = "development"
    service_name: str = "paperforge-api"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = True

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    opensearch: OpenSearchSettings = Field(default_factory=OpenSearchSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    ollama: OllamaSettings = Field(default_factory=OllamaSettings)


@lru_cache
def get_settings() -> Settings:
    """Return one immutable settings object per process."""

    return Settings()
