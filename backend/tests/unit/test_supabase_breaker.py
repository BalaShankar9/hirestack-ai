"""S1-F9: behavioral test — supabase breaker trips on consecutive transient errors.

Pins the contract:
  - 10 consecutive transient errors (httpx.TimeoutException) trip the
    "supabase" breaker.
  - Once tripped, the next _run() call raises CircuitBreakerOpen
    immediately without invoking the underlying function.
  - Non-transient errors do NOT trip the breaker.
"""
from __future__ import annotations

import httpx
import pytest

from app.core.circuit_breaker import (
    CircuitBreakerOpen,
    get_breaker_sync,
    reset_all_breakers,
)
from app.core.database import SupabaseDB


@pytest.fixture(autouse=True)
def _reset_breakers():
    reset_all_breakers()
    yield
    reset_all_breakers()


def _make_db() -> SupabaseDB:
    db = SupabaseDB.__new__(SupabaseDB)
    db.client = None  # type: ignore[assignment]
    return db


@pytest.mark.asyncio
async def test_consecutive_transient_failures_trip_supabase_breaker():
    """10 transient failures must open the breaker."""
    db = _make_db()

    def _fail():
        raise httpx.TimeoutException("simulated upstream timeout")

    # Force retries to 1 so each _run yields exactly one breaker failure.
    from app.core import config as _config

    original_retries = _config.settings.supabase_http_retries
    _config.settings.supabase_http_retries = 1
    try:
        for _ in range(10):
            with pytest.raises(httpx.TimeoutException):
                await db._run(_fail)

        # 11th call should be rejected by the breaker without invoking _fail.
        invoked = []

        def _spy():
            invoked.append(1)
            return "ok"

        with pytest.raises(CircuitBreakerOpen):
            await db._run(_spy)
        assert invoked == [], "breaker should have rejected without invoking the call"
    finally:
        _config.settings.supabase_http_retries = original_retries


@pytest.mark.asyncio
async def test_non_transient_error_does_not_trip_breaker():
    """A 100x business-logic error (e.g. validation) must not poison the breaker."""
    db = _make_db()

    def _bad():
        # Generic ValueError — not in _is_transient_error's match list.
        raise ValueError("unique constraint violated")

    for _ in range(20):
        with pytest.raises(ValueError):
            await db._run(_bad)

    breaker = get_breaker_sync("supabase")
    # Breaker must still be closed.
    from app.core.circuit_breaker import CircuitState

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_success_resets_supabase_breaker_failure_count():
    """A successful _run after a single failure must clear the failure counter."""
    db = _make_db()

    def _ok():
        return "ok"

    def _timeout():
        raise httpx.TimeoutException("blip")

    from app.core import config as _config

    original_retries = _config.settings.supabase_http_retries
    _config.settings.supabase_http_retries = 1
    try:
        with pytest.raises(httpx.TimeoutException):
            await db._run(_timeout)

        breaker = get_breaker_sync("supabase")
        assert breaker.failure_count == 1

        result = await db._run(_ok)
        assert result == "ok"
        assert breaker.failure_count == 0
    finally:
        _config.settings.supabase_http_retries = original_retries
