"""
HireStack AI - Configuration Module
Central configuration management using pydantic-settings
"""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        # Always load backend/.env regardless of cwd
        env_file=str(_BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Application
    app_name: str = "HireStack AI"
    app_version: str = "1.0.0"
    debug: bool = False
    environment: str = "development"
    sentry_dsn: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:3002"]
    allowed_origins: str = "http://localhost:3002"

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # Redis (optional - for caching)
    redis_url: str = "redis://localhost:6379"

    # AI Provider — Gemini only (legacy OpenAI/Ollama settings removed)
    ai_provider: str = "gemini"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    gemini_max_tokens: int = 8192

    # Gemini via Vertex AI (optional)
    # If enabled, GEMINI_API_KEY is ignored and the google.genai SDK will use
    # Application Default Credentials (ADC) for auth.
    gemini_use_vertexai: bool = False
    # Vertex AI mode (OAuth) — optional alternative to API key.
    # Provide these when GEMINI_USE_VERTEXAI=true.
    gemini_vertex_project: str = ""
    gemini_vertex_location: str = ""

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
