"""Application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings for Paperforge."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PAPERFORGE_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = True


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()
