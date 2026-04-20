"""GDPR / account-data endpoints.

Exposes:
  • ``GET /api/me/export``  — downloadable JSON of the authenticated user's
    primary data (profile, applications, documents metadata, career events).
    Covers GDPR Article 15 (Right to Access) + Article 20 (Data Portability).
  • ``DELETE /api/me``     — hard-deletes the authenticated user's account.
    Relies on the database ``ON DELETE CASCADE`` / ``SET NULL`` FK policy
    (see migration ``20260420200000_user_fk_on_delete_hygiene.sql``).
    Covers GDPR Article 17 (Right to Erasure).

These endpoints are intentionally thin: the heavy lifting (cascade) happens
in Postgres thanks to the FK hygiene migration. Both endpoints are
rate-limited and require an authenticated bearer token.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.database import TABLES, get_supabase
from app.core.security import limiter

logger = structlog.get_logger("hirestack.me")
router = APIRouter()


def _safe_select(db: Any, table: str, user_col: str, user_id: str) -> list:
    """Best-effort select that returns [] on any error (table/col missing)."""
    try:
        resp = db.table(table).select("*").eq(user_col, user_id).execute()
        return getattr(resp, "data", None) or []
    except Exception as exc:
        logger.warning("me.export.select_failed", table=table, error=str(exc)[:200])
        return []


@router.get("/me/export", tags=["Account"])
@limiter.limit("5/hour")
async def export_my_data(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Return a JSON export of the authenticated user's data.

    Limited to 5 requests/hour per IP to prevent scraping abuse.
    """
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    db = get_supabase()

    def _gather() -> Dict[str, Any]:
        return {
            "user_id": user_id,
            "profile": _safe_select(db, TABLES.get("users", "users"), "id", user_id),
            "applications": _safe_select(
                db, TABLES.get("applications", "applications"), "user_id", user_id
            ),
            "generation_jobs": _safe_select(
                db, TABLES.get("generation_jobs", "generation_jobs"), "user_id", user_id
            ),
            "resumes": _safe_select(
                db, TABLES.get("resumes", "resumes"), "user_id", user_id
            ),
            "documents": _safe_select(
                db, TABLES.get("documents", "documents"), "user_id", user_id
            ),
            "career_events": _safe_select(
                db, "career_events", "user_id", user_id
            ),
            "ai_generation_usage": _safe_select(
                db, "ai_generation_usage_daily", "user_id", user_id
            ),
        }

    data = await asyncio.to_thread(_gather)

    logger.info("me.export.completed", user_id=user_id,
                tables=len([k for k, v in data.items() if isinstance(v, list) and v]))
    return {
        "schema_version": 1,
        "generated_at_utc": None,  # set by client to avoid TZ confusion
        "data": data,
    }


@router.delete("/me", tags=["Account"], status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("3/hour")
async def delete_my_account(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> None:
    """Hard-delete the authenticated user's account.

    Cascades via Postgres FK policy:
      • Owned rows (applications, resumes, docs) CASCADE-delete.
      • Audit / billing rows SET NULL to preserve integrity evidence.

    Rate-limited aggressively (3/hour/IP) to prevent hostile-takeover abuse.
    This is irreversible — frontend MUST confirm intent before calling.
    """
    user_id = current_user.get("id")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    db = get_supabase()

    def _delete() -> int:
        resp = db.table(TABLES.get("users", "users")).delete().eq("id", user_id).execute()
        rows = getattr(resp, "data", None) or []
        return len(rows)

    try:
        deleted = await asyncio.to_thread(_delete)
    except Exception as exc:
        logger.error("me.delete.failed", user_id=user_id, error=str(exc)[:300])
        raise HTTPException(
            status_code=500,
            detail="Failed to delete account. Please contact support.",
        )

    logger.info("me.delete.completed", user_id=user_id, rows_deleted=deleted)
    return None
