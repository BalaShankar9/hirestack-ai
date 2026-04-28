"""S1-F2: behavioral tests for app.core.config.Settings.

Pin the production fail-fast contract:

  1. In ``ENVIRONMENT=production``, missing ``supabase_url``,
     ``supabase_anon_key``, ``supabase_service_role_key``, or
     ``supabase_jwt_secret`` raises a ValidationError at instantiation —
     the process must NOT start with empty Supabase credentials in prod.

  2. In any other environment (``development``, ``staging``, unset),
     the same fields default to empty strings and instantiation
     succeeds — no fail-fast outside production.

  3. ``get_settings()`` is cached: the second call returns the SAME
     instance (lru_cache contract — relied on by every importer).

  4. Default values match the documented contract: ``debug=False``,
     ``environment="development"``, ``ai_provider="gemini"``,
     ``cache_enabled=True``, ``rate_limit_requests=100``.

Pure-function tests, no I/O, no fixtures from other modules.
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# Production fail-fast contract (#1)
# ---------------------------------------------------------------------------

class TestProductionFailFast:
    """In production, empty critical Supabase fields must abort startup."""

    @pytest.mark.parametrize(
        "missing_field",
        [
            "SUPABASE_URL",
            "SUPABASE_ANON_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_JWT_SECRET",
        ],
    )
    def test_missing_critical_field_raises_in_production(self, missing_field: str) -> None:
        from app.core.config import Settings

        env = {
            "ENVIRONMENT": "production",
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "service",
            "SUPABASE_JWT_SECRET": "jwtsecret",
        }
        env[missing_field] = ""  # blank out the field under test

        with patch.dict(os.environ, env, clear=False):
            with pytest.raises(ValidationError) as exc_info:
                Settings(_env_file=None)

        # Error message identifies which field failed — operators must know.
        assert missing_field.lower().replace("_", "") in str(exc_info.value).lower().replace("_", "")

    def test_all_fields_present_in_production_succeeds(self) -> None:
        from app.core.config import Settings

        env = {
            "ENVIRONMENT": "production",
            "SUPABASE_URL": "https://x.supabase.co",
            "SUPABASE_ANON_KEY": "anon",
            "SUPABASE_SERVICE_ROLE_KEY": "service",
            "SUPABASE_JWT_SECRET": "jwtsecret",
        }

        with patch.dict(os.environ, env, clear=False):
            s = Settings(_env_file=None)

        assert s.environment == "production"
        assert s.supabase_url == "https://x.supabase.co"
        assert s.supabase_jwt_secret == "jwtsecret"


# ---------------------------------------------------------------------------
# Non-production tolerance (#2)
# ---------------------------------------------------------------------------

class TestNonProductionTolerance:
    """Empty Supabase fields are fine in dev/staging/unset envs."""

    @pytest.mark.parametrize("env_name", ["development", "staging", "test", ""])
    def test_empty_supabase_fields_allowed_outside_production(self, env_name: str) -> None:
        from app.core.config import Settings

        env = {
            "ENVIRONMENT": env_name,
            "SUPABASE_URL": "",
            "SUPABASE_ANON_KEY": "",
            "SUPABASE_SERVICE_ROLE_KEY": "",
            "SUPABASE_JWT_SECRET": "",
        }

        with patch.dict(os.environ, env, clear=False):
            s = Settings(_env_file=None)

        assert s.supabase_url == ""
        assert s.supabase_jwt_secret == ""


# ---------------------------------------------------------------------------
# get_settings() caching contract (#3)
# ---------------------------------------------------------------------------

class TestGetSettingsCache:
    def test_get_settings_returns_singleton(self) -> None:
        from app.core.config import get_settings

        a = get_settings()
        b = get_settings()
        assert a is b, "get_settings() must be lru_cache'd — importers rely on identity"


# ---------------------------------------------------------------------------
# Default values (#4)
# ---------------------------------------------------------------------------

class TestDefaults:
    """Documented defaults must not drift silently."""

    def test_documented_defaults(self) -> None:
        from app.core.config import Settings

        # Force a clean instantiation with no env overrides for defaulted fields.
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SUPABASE_URL": "",
                "SUPABASE_ANON_KEY": "",
                "SUPABASE_SERVICE_ROLE_KEY": "",
                "SUPABASE_JWT_SECRET": "",
            },
            clear=False,
        ):
            # Strip env overrides that would mask defaults.
            for key in (
                "DEBUG",
                "AI_PROVIDER",
                "CACHE_ENABLED",
                "RATE_LIMIT_REQUESTS",
                "RATE_LIMIT_WINDOW",
                "PORT",
                "MAX_UPLOAD_SIZE_MB",
            ):
                os.environ.pop(key, None)
            s = Settings(_env_file=None)

        assert s.debug is False
        assert s.environment == "development"
        assert s.ai_provider == "gemini"
        assert s.cache_enabled is True
        assert s.ai_cache_enabled is True
        assert s.rate_limit_requests == 100
        assert s.rate_limit_window == 60
        assert s.port == 8000
        assert s.max_upload_size_mb == 10
        assert ".pdf" in s.allowed_file_types
        assert s.app_name == "HireStack AI"

    def test_cors_origins_includes_production_domains(self) -> None:
        from app.core.config import Settings

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            s = Settings(_env_file=None)

        assert "https://hirestack.tech" in s.cors_origins
        assert "https://www.hirestack.tech" in s.cors_origins
        assert "http://localhost:3000" in s.cors_origins


# ---------------------------------------------------------------------------
# S1-F7: stray getenvs absorbed into Settings
# ---------------------------------------------------------------------------

class TestF7StrayEnvFields:
    """Pin that retry / queue / worker tuning lives in Settings, not bare os.getenv."""

    def test_supabase_http_retry_defaults(self) -> None:
        from app.core.config import Settings

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            for k in (
                "SUPABASE_HTTP_RETRIES",
                "SUPABASE_HTTP_RETRY_BASE_S",
                "SUPABASE_HTTP_RETRY_MAX_S",
            ):
                os.environ.pop(k, None)
            s = Settings(_env_file=None)
        assert s.supabase_http_retries == 3
        assert s.supabase_http_retry_base_s == 0.25
        assert s.supabase_http_retry_max_s == 2.0

    def test_supabase_http_retries_clamped_to_min_one(self) -> None:
        from app.core.config import Settings

        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "SUPABASE_HTTP_RETRIES": "0"},
            clear=False,
        ):
            s = Settings(_env_file=None)
        assert s.supabase_http_retries == 1

    def test_supabase_http_retry_base_clamped_to_min(self) -> None:
        from app.core.config import Settings

        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "SUPABASE_HTTP_RETRY_BASE_S": "0.001"},
            clear=False,
        ):
            s = Settings(_env_file=None)
        assert s.supabase_http_retry_base_s == 0.05

    def test_queue_require_active_consumer_default_true(self) -> None:
        from app.core.config import Settings

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            os.environ.pop("QUEUE_REQUIRE_ACTIVE_CONSUMER", None)
            s = Settings(_env_file=None)
        assert s.queue_require_active_consumer is True

    def test_queue_require_active_consumer_disable(self) -> None:
        from app.core.config import Settings

        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "QUEUE_REQUIRE_ACTIVE_CONSUMER": "false"},
            clear=False,
        ):
            s = Settings(_env_file=None)
        assert s.queue_require_active_consumer is False

    def test_worker_defaults(self) -> None:
        from app.core.config import Settings

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            for k in ("WORKER_NAME", "WORKER_CONCURRENCY"):
                os.environ.pop(k, None)
            s = Settings(_env_file=None)
        assert s.worker_name == "worker-1"
        assert s.worker_concurrency == 3

    def test_worker_concurrency_clamped_to_min_one(self) -> None:
        from app.core.config import Settings

        with patch.dict(
            os.environ,
            {"ENVIRONMENT": "development", "WORKER_CONCURRENCY": "0"},
            clear=False,
        ):
            s = Settings(_env_file=None)
        assert s.worker_concurrency == 1

