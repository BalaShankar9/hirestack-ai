"""Usage-guard backstop for AI generation cost control.

Enforces caps that ALWAYS apply, regardless of billing flag state:

  • Per-user daily generation cap (default 20/day, env override)
  • Platform-wide daily AI-spend circuit breaker (default $500/day,
    env override). When the platform cap is hit, ALL generation is
    paused until UTC midnight.

Both counters live in Supabase tables created by migration
``20260420300000_usage_guard_tables.sql``.

This is a *backstop* — it runs BEFORE ``check_billing_limit`` in the
four generation entrypoints, so even when billing is disabled or the
user has no org, abusers cannot burn unlimited AI.

Env overrides:
  USAGE_GUARD_USER_DAILY_CAP   (default: 20)
  USAGE_GUARD_PLATFORM_DAILY_CAP_CENTS  (default: 50_000 = $500)
  USAGE_GUARD_ENABLED          (default: "true" — "false" disables all checks)
"""
from __future__ import annotations

import os
from datetime import date
from typing import Any, Dict

import structlog

logger = structlog.get_logger("hirestack.usage_guard")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("usage_guard.bad_env", name=name, value=raw)
        return default


def _env_enabled() -> bool:
    return os.environ.get("USAGE_GUARD_ENABLED", "true").strip().lower() in (
        "true", "1", "yes", "on",
    )


def _user_daily_cap() -> int:
    return _env_int("USAGE_GUARD_USER_DAILY_CAP", 20)


def _platform_daily_cap_cents() -> int:
    return _env_int("USAGE_GUARD_PLATFORM_DAILY_CAP_CENTS", 50_000)


class UsageGuardExceeded(Exception):
    """Raised when a backstop cap is hit. Carries an HTTP-friendly payload."""

    def __init__(self, *, scope: str, limit: int, actual: int, retry_after_hours: int = 0):
        self.scope = scope          # "user_daily" | "platform_daily"
        self.limit = limit
        self.actual = actual
        self.retry_after_hours = retry_after_hours
        super().__init__(
            f"usage_guard {scope} exceeded: {actual}/{limit}"
        )


async def check_and_reserve(user_id: str) -> Dict[str, Any]:
    """Check both caps, raise UsageGuardExceeded on hit.

    Does not increment counters — call ``record_generation`` after the job
    has been successfully enqueued so failed enqueues don't consume quota.

    Returns a dict with current usage info for logging/telemetry.
    """
    if not _env_enabled():
        return {"enforced": False}

    user_cap = _user_daily_cap()
    plat_cap_cents = _platform_daily_cap_cents()
    today = date.today().isoformat()

    # Lazy import to avoid circular deps
    from app.core.database import get_supabase

    db = get_supabase()

    # Per-user cap — read row, raise if at/over
    try:
        user_row = await _get_user_row(db, user_id, today)
    except Exception as exc:
        # Fail-open on DB read error — availability > strict enforcement
        logger.warning("usage_guard.read_failed", user_id=user_id, error=str(exc)[:200])
        return {"enforced": False, "error": "read_failed"}

    user_count = int(user_row.get("generation_count", 0)) if user_row else 0
    if user_count >= user_cap:
        raise UsageGuardExceeded(
            scope="user_daily",
            limit=user_cap,
            actual=user_count,
            retry_after_hours=24,
        )

    # Platform cap
    try:
        plat_row = await _get_platform_row(db, today)
    except Exception as exc:
        logger.warning("usage_guard.platform_read_failed", error=str(exc)[:200])
        return {
            "enforced": True,
            "user_count": user_count,
            "user_cap": user_cap,
            "platform_cents": 0,
            "platform_cap_cents": plat_cap_cents,
        }

    plat_cents = int(plat_row.get("cost_cents", 0)) if plat_row else 0
    if plat_cents >= plat_cap_cents:
        raise UsageGuardExceeded(
            scope="platform_daily",
            limit=plat_cap_cents,
            actual=plat_cents,
            retry_after_hours=24,
        )

    return {
        "enforced": True,
        "user_count": user_count,
        "user_cap": user_cap,
        "platform_cents": plat_cents,
        "platform_cap_cents": plat_cap_cents,
    }


async def record_generation(
    user_id: str,
    *,
    cost_cents: int = 0,
    token_total: int = 0,
) -> None:
    """Increment both counters after a generation was started/completed.

    Best-effort — logs and swallows errors so counter-update failures
    never break the generation flow.
    """
    if not _env_enabled():
        return

    today = date.today().isoformat()

    try:
        from app.core.database import get_supabase
        db = get_supabase()
    except Exception as exc:
        logger.warning("usage_guard.db_unavailable", error=str(exc)[:200])
        return

    try:
        await _upsert_user_row(db, user_id, today, cost_cents, token_total)
    except Exception as exc:
        logger.warning(
            "usage_guard.user_upsert_failed",
            user_id=user_id,
            error=str(exc)[:200],
        )

    try:
        await _upsert_platform_row(db, today, cost_cents, token_total)
    except Exception as exc:
        logger.warning("usage_guard.platform_upsert_failed", error=str(exc)[:200])


# ── Internals (split for testability) ──────────────────────────────────
async def _get_user_row(db: Any, user_id: str, today: str) -> Dict[str, Any] | None:
    import asyncio

    def _q():
        return (
            db.table("ai_generation_usage_daily")
            .select("generation_count, token_total, cost_cents")
            .eq("user_id", user_id)
            .eq("usage_date", today)
            .limit(1)
            .execute()
        )

    resp = await asyncio.to_thread(_q)
    data = getattr(resp, "data", None) or []
    return data[0] if data else None


async def _get_platform_row(db: Any, today: str) -> Dict[str, Any] | None:
    import asyncio

    def _q():
        return (
            db.table("ai_platform_spend_daily")
            .select("generation_count, cost_cents, token_total")
            .eq("spend_date", today)
            .limit(1)
            .execute()
        )

    resp = await asyncio.to_thread(_q)
    data = getattr(resp, "data", None) or []
    return data[0] if data else None


async def _upsert_user_row(
    db: Any, user_id: str, today: str, cost_cents: int, token_total: int
) -> None:
    import asyncio

    def _q():
        # Read-modify-write. Supabase Python client doesn't have native upsert-and-increment.
        existing = (
            db.table("ai_generation_usage_daily")
            .select("generation_count, token_total, cost_cents")
            .eq("user_id", user_id)
            .eq("usage_date", today)
            .limit(1)
            .execute()
        )
        rows = getattr(existing, "data", None) or []
        if rows:
            current = rows[0]
            db.table("ai_generation_usage_daily").update(
                {
                    "generation_count": int(current.get("generation_count", 0)) + 1,
                    "token_total": int(current.get("token_total", 0)) + token_total,
                    "cost_cents": int(current.get("cost_cents", 0)) + cost_cents,
                    "updated_at": "now()",
                }
            ).eq("user_id", user_id).eq("usage_date", today).execute()
        else:
            db.table("ai_generation_usage_daily").insert(
                {
                    "user_id": user_id,
                    "usage_date": today,
                    "generation_count": 1,
                    "token_total": token_total,
                    "cost_cents": cost_cents,
                }
            ).execute()

    await asyncio.to_thread(_q)


async def _upsert_platform_row(
    db: Any, today: str, cost_cents: int, token_total: int
) -> None:
    import asyncio

    def _q():
        existing = (
            db.table("ai_platform_spend_daily")
            .select("generation_count, token_total, cost_cents")
            .eq("spend_date", today)
            .limit(1)
            .execute()
        )
        rows = getattr(existing, "data", None) or []
        if rows:
            current = rows[0]
            db.table("ai_platform_spend_daily").update(
                {
                    "generation_count": int(current.get("generation_count", 0)) + 1,
                    "token_total": int(current.get("token_total", 0)) + token_total,
                    "cost_cents": int(current.get("cost_cents", 0)) + cost_cents,
                    "updated_at": "now()",
                }
            ).eq("spend_date", today).execute()
        else:
            db.table("ai_platform_spend_daily").insert(
                {
                    "spend_date": today,
                    "generation_count": 1,
                    "token_total": token_total,
                    "cost_cents": cost_cents,
                }
            ).execute()

    await asyncio.to_thread(_q)


__all__ = [
    "UsageGuardExceeded",
    "check_and_reserve",
    "record_generation",
]
