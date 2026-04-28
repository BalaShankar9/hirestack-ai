"""Anchor tests for usage_guard backstop and GDPR /me endpoints.

These tests intentionally mock Supabase at the helper boundary so the
enforcement logic can be verified in isolation from network I/O.
"""
from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, patch

import pytest

from app.api.deps import check_usage_guard
from app.services import usage_guard


# ── Usage guard: cap math ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_usage_guard_raises_when_user_daily_cap_exceeded(monkeypatch):
    monkeypatch.setenv("USAGE_GUARD_USER_DAILY_CAP", "5")
    monkeypatch.setenv("USAGE_GUARD_ENABLED", "true")

    with patch.object(
        usage_guard,
        "_get_user_row",
        new=AsyncMock(return_value={"generation_count": 5}),
    ):
        with pytest.raises(usage_guard.UsageGuardExceeded) as exc_info:
            await usage_guard.check_and_reserve("user-1")

    assert exc_info.value.scope == "user_daily"
    assert exc_info.value.limit == 5
    assert exc_info.value.actual == 5


@pytest.mark.asyncio
async def test_usage_guard_allows_when_under_cap(monkeypatch):
    monkeypatch.setenv("USAGE_GUARD_USER_DAILY_CAP", "5")
    monkeypatch.setenv("USAGE_GUARD_ENABLED", "true")

    with patch.object(
        usage_guard,
        "_get_user_row",
        new=AsyncMock(return_value={"generation_count": 2}),
    ), patch.object(
        usage_guard,
        "_get_platform_row",
        new=AsyncMock(return_value={"cost_cents": 100}),
    ):
        result = await usage_guard.check_and_reserve("user-1")

    assert result["enforced"] is True
    assert result["user_count"] == 2


@pytest.mark.asyncio
async def test_usage_guard_platform_cap_blocks_all_users(monkeypatch):
    monkeypatch.setenv("USAGE_GUARD_USER_DAILY_CAP", "100")
    monkeypatch.setenv("USAGE_GUARD_PLATFORM_DAILY_CAP_CENTS", "10000")
    monkeypatch.setenv("USAGE_GUARD_ENABLED", "true")

    with patch.object(
        usage_guard,
        "_get_user_row",
        new=AsyncMock(return_value={"generation_count": 1}),
    ), patch.object(
        usage_guard,
        "_get_platform_row",
        new=AsyncMock(return_value={"cost_cents": 10000}),
    ):
        with pytest.raises(usage_guard.UsageGuardExceeded) as exc_info:
            await usage_guard.check_and_reserve("user-1")

    assert exc_info.value.scope == "platform_daily"


@pytest.mark.asyncio
async def test_usage_guard_can_be_disabled_via_env(monkeypatch):
    monkeypatch.setenv("USAGE_GUARD_ENABLED", "false")
    result = await usage_guard.check_and_reserve("user-1")
    assert result == {"enforced": False}


@pytest.mark.asyncio
async def test_usage_guard_fails_open_on_db_error(monkeypatch):
    monkeypatch.setenv("USAGE_GUARD_ENABLED", "true")
    monkeypatch.setenv("USAGE_GUARD_USER_DAILY_CAP", "5")

    async def _boom(*args, **kwargs):
        raise RuntimeError("db down")

    with patch.object(usage_guard, "_get_user_row", new=_boom):
        result = await usage_guard.check_and_reserve("user-1")

    assert result == {"enforced": False, "error": "read_failed"}


# ── deps.check_usage_guard raises 429 HTTPException ───────────────────

@pytest.mark.asyncio
async def test_check_usage_guard_raises_429_on_cap_hit(monkeypatch):
    from fastapi import HTTPException

    async def _boom(_uid):
        raise usage_guard.UsageGuardExceeded(
            scope="user_daily", limit=5, actual=5, retry_after_hours=24
        )

    with patch.object(usage_guard, "check_and_reserve", new=_boom):
        with pytest.raises(HTTPException) as exc_info:
            await check_usage_guard({"id": "user-1"})

    assert exc_info.value.status_code == 429
    assert exc_info.value.detail["scope"] == "user_daily"
    assert exc_info.value.detail["limit"] == 5


# ── Anti-drift: all generation entrypoints must call check_usage_guard ─

def test_generation_entrypoints_invoke_usage_guard():
    """Every AI-spend entrypoint must call check_usage_guard. Anti-drift."""
    from app.api.routes.generate import planned, document, sync_pipeline, stream, jobs

    for mod in (planned, document, sync_pipeline, stream, jobs):
        src = inspect.getsource(mod)
        assert "check_usage_guard" in src, (
            f"{mod.__name__} must call check_usage_guard before billing"
        )


# ── /me router is registered ──────────────────────────────────────────

def test_me_router_is_registered():
    from app.api.routes import router

    paths = {getattr(r, "path", "") for r in router.routes}
    assert any("/me" in p for p in paths), "GDPR /me endpoints must be registered"
