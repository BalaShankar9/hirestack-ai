"""
HireStack AI - Configuration Module
Central configuration management using pydantic-settings
"""
from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    app_name: str = "HireStack AI"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "https://hirestack.ai"]
    allowed_origins: str = "http://localhost:3000"

    # Firebase
    firebase_project_id: str = "hirestack-ai"
    firebase_credentials_path: Optional[str] = None  # Path to service account JSON
    firebase_database_id: str = "default"  # Firestore multi-db ID (new projects often use `default`)
    firebase_storage_bucket: Optional[str] = None  # e.g. "<project-id>.appspot.com" or "<project-id>.firebasestorage.app"

    # Redis (optional - for caching)
    redis_url: str = "redis://localhost:6379"

    # Anthropic (Claude)
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_max_tokens: int = 4096

    # File Upload
    max_upload_size_mb: int = 10
    allowed_file_types: List[str] = [".pdf", ".docx", ".doc", ".txt"]
    upload_dir: str = "./uploads"

    # Rate Limiting
    rate_limit_requests: int = 100
    rate_limit_window: int = 60  # seconds


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
