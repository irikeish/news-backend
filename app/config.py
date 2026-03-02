"""Centralized configuration from environment with validation."""

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment.

    MongoDB: Set MONGODB_URL for full URL, or use MONGO_* vars (from .env).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    mongodb_url: str = Field(
        default="",
        description="MongoDB connection URL (optional; built from MONGO_* when empty)",
    )
    mongodb_db: str = Field(
        default="news",
        validation_alias=AliasChoices("MONGODB_DB", "MONGO_DB"),
        description="Database name",
    )
    mongodb_auth_source: str = Field(
        default="admin", description="MongoDB authentication source"
    )
    mongo_host: str = Field(default="localhost", description="MongoDB host")
    mongo_port: int = Field(default=27017, description="MongoDB port")
    mongo_user: str = Field(default="", description="MongoDB user (auth)")
    mongo_password: str = Field(default="", description="MongoDB password (auth)")

    @computed_field
    @property
    def resolved_mongodb_url(self) -> str:
        """MongoDB URL with auth when credentials are in .env."""
        if self.mongodb_url:
            return self.mongodb_url
        if self.mongo_user and self.mongo_password:
            return (
                f"mongodb://{self.mongo_user}:{self.mongo_password}"
                f"@{self.mongo_host}:{self.mongo_port}/{self.mongodb_db}?authSource={self.mongodb_auth_source}"
            )
        return f"mongodb://{self.mongo_host}:{self.mongo_port}"

    openai_api_key: str = Field(
        default="", description="OpenAI API key (required for LLM)"
    )
    openai_model: str = Field(
        default="gpt-4o-mini",
        min_length=1,
        description="OpenAI model for parsing and summarization",
    )

    valkey_url: str = Field(
        default="redis://valkey:6379",
        description="Valkey/Redis connection URL",
    )

    cache_backend: Literal["memory", "valkey", "none"] = Field(
        default="memory",
        description="Cache backend: memory, valkey, or none",
    )
    nominatim_user_agent: str = Field(
        default="News-App/1.0",
        description="User-Agent for Nominatim API (required by usage policy)",
    )

    default_radius_km: float = Field(
        default=10.0,
        gt=0,
        description="Default radius for nearby/trending queries (km)",
    )
    max_radius_km: float = Field(
        default=1500.0,
        gt=0,
        le=2000.0,
        description="Max radius for nearby/trending queries (km)",
    )
    top_n: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Default number of articles to return",
    )
    news_buffer_days: int = Field(
        default=7,
        ge=1,
        description="Only show articles published within this many days",
    )


@lru_cache
def get_settings() -> Settings:
    """Return cached settings singleton."""
    return Settings()


settings = get_settings()
