"""Phase D.2 / D.3 — variant lock endpoints (CV + personal statement).

After a generation run completes, the application row contains
``cv_versions`` and/or ``ps_versions`` JSONB arrays of variants
(concise, narrative).  Within each list, one is marked ``locked: True``
by convention and its content lives in the canonical column
(``cv_html`` / ``personal_statement_html``).  These endpoints flip
the lock to a different variant and atomically swap the canonical
column so the rest of the app keeps reading from a single source of
truth.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List, Tuple

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.core.database import TABLES, get_supabase
from app.core.security import limiter

from .helpers import logger

router = APIRouter()


async def _lock_variant_generic(
    *,
    application_id: str,
    variant_key: str,
    user_id: str,
    versions_column: str,
    canonical_column: str,
    log_label: str,
) -> Tuple[List[Dict[str, Any]], str]:
    """Shared lock implementation.

    Returns ``(new_variants, new_canonical_html)``.  Raises
    :class:`HTTPException` for 404/409 cases.
    """
    sb = get_supabase()

    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select(f"id,user_id,{canonical_column},{versions_column}")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp or not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data = app_resp.data
    variants_raw = app_data.get(versions_column) or []
    if not isinstance(variants_raw, list) or not variants_raw:
        raise HTTPException(
            status_code=409,
            detail=f"Application has no {log_label} variants to lock",
        )

    target = next(
        (v for v in variants_raw if isinstance(v, dict) and v.get("variant") == variant_key),
        None,
    )
    if target is None:
        available = [v.get("variant") for v in variants_raw if isinstance(v, dict)]
        raise HTTPException(
            status_code=404,
            detail=f"Variant '{variant_key}' not found. Available: {available}",
        )
    if not (target.get("content") or "").strip():
        raise HTTPException(
            status_code=409,
            detail=f"Variant '{variant_key}' has empty content; cannot lock",
        )

    locked_at = datetime.utcnow().isoformat() + "Z"
    new_variants: List[Dict[str, Any]] = []
    for v in variants_raw:
        if not isinstance(v, dict):
            continue
        is_target = v.get("variant") == variant_key
        new_variants.append({
            **v,
            "locked": is_target,
            **({"locked_at": locked_at} if is_target else {}),
        })

    new_html = target["content"]
    patch = {
        versions_column: new_variants,
        canonical_column: new_html,
        "updated_at": locked_at,
    }
    await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .update(patch)
        .eq("id", application_id)
        .eq("user_id", user_id)
        .execute()
    )
    logger.info(
        f"{log_label}_variant.locked",
        application_id=application_id,
        variant=variant_key,
        user_id=user_id,
    )
    return new_variants, new_html


@router.post("/applications/{application_id}/cv-variants/{variant_key}/lock")
@limiter.limit("30/minute")
async def lock_cv_variant(
    request: Request,
    application_id: str,
    variant_key: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lock a CV variant: flip flags and copy its content into ``cv_html``."""
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    new_variants, new_html = await _lock_variant_generic(
        application_id=application_id,
        variant_key=variant_key,
        user_id=user_id,
        versions_column="cv_versions",
        canonical_column="cv_html",
        log_label="cv",
    )
    return {
        "applicationId": application_id,
        "lockedVariant": variant_key,
        "cvHtml": new_html,
        "cvVariants": new_variants,
    }


@router.post("/applications/{application_id}/ps-variants/{variant_key}/lock")
@limiter.limit("30/minute")
async def lock_ps_variant(
    request: Request,
    application_id: str,
    variant_key: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lock a Personal Statement variant: flip flags and copy its content
    into ``personal_statement_html``."""
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    new_variants, new_html = await _lock_variant_generic(
        application_id=application_id,
        variant_key=variant_key,
        user_id=user_id,
        versions_column="ps_versions",
        canonical_column="personal_statement_html",
        log_label="ps",
    )
    return {
        "applicationId": application_id,
        "lockedVariant": variant_key,
        "personalStatementHtml": new_html,
        "personalStatementVariants": new_variants,
    }
