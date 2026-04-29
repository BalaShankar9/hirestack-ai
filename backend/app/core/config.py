"""
HireStack AI - Configuration Module
Central configuration management using pydantic-settings
"""
from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _read_version() -> str:
    """Read the canonical app version from ``backend/VERSION``.

    The VERSION file is the single source of truth (S12-F2). Bumping it
    bumps Sentry ``release``, the ``/health`` payload, and the
    ``X-App-Version`` header in lock-step. If the file is missing or
    empty we fall back to ``"0.0.0"`` so no import-time crash can take
    the process down — the contract test ``test_version_file_contract``
    guards the file itself.
    """
    version_file = _BACKEND_ROOT / "VERSION"
    try:
        text = version_file.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return text or "0.0.0"


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
    app_version: str = _read_version()
    debug: bool = False
    environment: str = "development"
    sentry_dsn: str = ""

    # Observability — when set, /metrics requires Bearer token. In
    # production this MUST be set or /metrics returns 403. In
    # development/test it may be left empty (open access).
    metrics_auth_token: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS
    cors_origins: List[str] = [
        "http://localhost:3000",
        "http://localhost:3002",
        "https://hirestack.tech",
        "https://www.hirestack.tech",
        "https://api.hirestack.tech",
        "https://hirestack-ai.netlify.app",
    ]

    # Supabase
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    supabase_jwt_secret: str = ""

    # Redis (optional - for caching and job queue)
    redis_url: str = "redis://localhost:6379"
    cache_ttl_seconds: int = 300  # default TTL for cached responses
    cache_enabled: bool = True  # can disable caching globally

    # AI Provider — Gemini only (legacy OpenAI/Ollama settings removed)
    ai_provider: str = "gemini"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-pro"
    gemini_max_tokens: int = 8192

    # AI Cost Controls
    ai_cache_enabled: bool = True  # semantic response caching
    ai_cache_ttl_seconds: int = 3600  # 1h TTL for AI response cache
    ai_cache_max_entries: int = 2000  # max in-memory cache entries
    ai_max_tokens_per_day: int = 10_000_000  # daily token budget (0=unlimited)
    ai_cost_alert_threshold_usd: float = 50.0  # log alert when daily cost exceeds this
    ai_max_input_tokens: int = 50_000  # truncate inputs longer than this

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

    # Supabase HTTP retry tuning (used by SupabaseDB._run)
    supabase_http_retries: int = 3
    supabase_http_retry_base_s: float = 0.25
    supabase_http_retry_max_s: float = 2.0

    # Job queue
    queue_require_active_consumer: bool = True

    # Worker
    worker_name: str = "worker-1"
    worker_concurrency: int = 3

    @field_validator("supabase_http_retries")
    @classmethod
    def _clamp_retries(cls, v: int) -> int:
        return max(1, int(v))

    @field_validator("supabase_http_retry_base_s")
    @classmethod
    def _clamp_retry_base(cls, v: float) -> float:
        return max(0.05, float(v))

    @field_validator("worker_concurrency")
    @classmethod
    def _clamp_worker_concurrency(cls, v: int) -> int:
        return max(1, int(v))

    @field_validator("supabase_url", "supabase_service_role_key", "supabase_anon_key")
    @classmethod
    def _require_in_production(cls, v: str, info) -> str:
        """Fail fast if critical Supabase values are empty in production."""
        import os
        if not v and os.getenv("ENVIRONMENT", "development") == "production":
            raise ValueError(f"{info.field_name} must be set in production")
        return v

    @field_validator("supabase_jwt_secret")
    @classmethod
    def _require_jwt_secret_in_production(cls, v: str, info) -> str:
        """Fail fast if JWT secret is empty in production."""
        import os
        if not v and os.getenv("ENVIRONMENT", "development") == "production":
            raise ValueError("supabase_jwt_secret must be set in production for JWT verification")
        return v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
