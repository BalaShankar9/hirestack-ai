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

    # ADR-0038 (P0-2): in-process dispatch fallback. Default OFF in
    # production — when Redis is unavailable the job is marked failed
    # with a retryable message instead of running on the web fleet.
    # Set to True only for dev / single-process deploys.
    ff_inprocess_fallback: bool = False
    # Hard cap on concurrent in-process generation jobs when the
    # fallback flag is on. Over-cap requests are failed fast.
    inprocess_max_concurrent: int = 4

    # ADR-0040 (P0-3): ACK Redis Stream messages only after handler
    # returns success. Default OFF — when False the consumer keeps the
    # legacy always-ACK-in-finally behaviour. Flip ON per-environment
    # after the processed_queue_events migration ships. Sunset
    # 2026-09-01.
    ff_queue_ack_on_success: bool = False
    # Max XPENDING deliveries before a message is routed to the shared
    # `events:dlq` stream and ACKed off the source. Only consulted when
    # ff_queue_ack_on_success is True.
    queue_max_deliveries: int = 5

    # Worker
    worker_name: str = "worker-1"
    worker_concurrency: int = 3

    # Background career monitor
    career_monitor_background_enabled: bool = True
    career_monitor_interval_seconds: int = 900
    career_monitor_user_batch_size: int = 20

    # PR m1-pr3: Idempotency-Key middleware. Default off for safe rollout;
    # flip on per-environment after migration ships.
    idempotency_enabled: bool = False

    # PR m2-pr6: scheduler extraction. While True (default), the web
    # process keeps running periodic sweeps + JobWatchdog inline — same
    # behaviour as before the split. Flip to False once the dedicated
    # `scheduler` process (app.scheduler.main) is deployed and verified
    # holding the leader lock; the web process will then skip the loops
    # and the scheduler is the sole runner. Rollback by setting
    # LEGACY_INPROC_SCHEDULER=true in the environment.
    legacy_inproc_scheduler: bool = True

    # PR m3-pr9: outbox relay. Default off — when False, the
    # `outbox_relay` Procfile process exits cleanly so the entry can be
    # deployed before the flag is flipped. Flip ON once producers are
    # wired (PR-9b) and the events_outbox table is being populated.
    ff_outbox_relay: bool = False

    # PR m3-pr10: event consumer scaffold. Default off — `event_consumer`
    # Procfile entries exit cleanly when False. Flip ON once a real
    # consumer (e.g. billing_usage) has its downstream side-effect wired
    # and the producers are publishing onto the matching streams.
    ff_event_consumer: bool = False

    # PR m6-pr18: Temporal generation strangler. Default off — when
    # False, /generate/jobs uses the legacy Redis-stream + in-process
    # fallback path. When True AND TEMPORAL_HOST is set, the route
    # dispatches `GenerationWorkflow` to the configured task queue. The
    # check is belt-and-braces: missing Temporal config causes graceful
    # fallback to legacy so a misconfigured deploy can never wedge the
    # generation pipeline. Rollout: dev → internal orgs → 5% → 50% →
    # 100% → 2 weeks → delete legacy path.
    ff_temporal_generation: bool = False

    # PR m6-pr19: AIM RAG over pgvector source embeddings. Default off
    # — when False the AIM reviewer runs without retrieved-source
    # context and the `aim_source_embed` consumer exits cleanly. When
    # True (and ff_event_consumer is also True) new aim_sources rows
    # are embedded asynchronously and the reviewer pulls top-k matches
    # via the `aim_sources_match` RPC. Backfill of existing rows is a
    # follow-up wave once the consumer is steady-state.
    ff_aim_rag: bool = False

    # PR m7-pr29 (ADR-0032): capability tokens for tool dispatch.
    # Default OFF — when False the dispatcher ignores any token passed
    # to ``invoke()`` UNLESS the per-tool ``requires_capability_token``
    # column is True (kill-switch path always enforced). When True every
    # tool with the per-tool flag is enforced AND any tool that ships a
    # token gets verified. Sunset 2026-09-01 (default ON, then remove
    # the flag once every L1+ tool is on capability tokens).
    ff_tool_capability_tokens: bool = False
    # Active HMAC key for capability tokens. Required when the flag is
    # ON or any tool sets requires_capability_token=True. Empty string
    # disables both mint and verify.
    tool_capability_secret: str = ""
    # Verify-only previous key for rotation overlap. When set, verify
    # accepts tokens signed with either secret; mint always uses the
    # active one. Drop after the rotation window closes.
    tool_capability_secret_previous: str = ""
    # Default mint TTL (seconds). Per-call override allowed up to
    # ``tool_capability_max_ttl_seconds``.
    tool_capability_default_ttl_seconds: int = 60
    tool_capability_max_ttl_seconds: int = 300

    # PR m7-pr29 (ADR-0033): sandbox tier routing. Default OFF — when
    # False every dispatch goes through L0 regardless of
    # ``record.sandbox_tier`` (tier is shadow-logged so we can see what
    # would have routed). When True the dispatcher consults the tier
    # column and picks the matching sandbox; L1 currently logs
    # ``tool_sandbox_l1_unenforced`` and falls through to L0 (real
    # host-blocking lands in m7-pr29b). Sunset 2026-09-01.
    ff_tool_sandbox_tier_routing: bool = False

    # PR m7-pr28 (ADR-0031): Anthropic as the cascade-tail provider so
    # tier-1 generations can survive a Gemini-wide outage. Default OFF.
    # When True, ``model_router.resolve_cascade`` exposes ``claude-*``
    # entries and ``AIClient._select_provider`` dispatches them through
    # ``_AnthropicProvider``. Anthropic is NEVER a primary route — it
    # only gets traffic when every Gemini SKU in the cascade has failed.
    # Sunset 2026-09-01.
    ff_anthropic_provider: bool = False
    anthropic_api_key: str = ""
    anthropic_default_model: str = "claude-3-5-sonnet-20241022"
    anthropic_max_tokens: int = 8192

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

    @field_validator("inprocess_max_concurrent")
    @classmethod
    def _clamp_inprocess_max_concurrent(cls, v: int) -> int:
        return max(1, int(v))

    @field_validator("queue_max_deliveries")
    @classmethod
    def _clamp_queue_max_deliveries(cls, v: int) -> int:
        return max(1, int(v))

    @field_validator("career_monitor_interval_seconds")
    @classmethod
    def _clamp_career_monitor_interval(cls, v: int) -> int:
        return max(60, int(v))

    @field_validator("career_monitor_user_batch_size")
    @classmethod
    def _clamp_career_monitor_user_batch_size(cls, v: int) -> int:
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
