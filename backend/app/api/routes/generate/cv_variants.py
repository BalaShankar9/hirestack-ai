"""Phase D.2 — CV variant lock endpoint.

After a generation run completes, the application row contains an
``cv_versions`` JSONB array of CV variants (concise, narrative).  One
is marked ``locked: True`` by convention and its content lives in
``cv_html``.  This endpoint lets the user flip the lock to a different
variant and atomically swap ``cv_html``.
"""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import get_current_user
from app.core.database import TABLES, get_supabase
from app.core.security import limiter

from .helpers import logger

router = APIRouter()


@router.post("/applications/{application_id}/cv-variants/{variant_key}/lock")
@limiter.limit("30/minute")
async def lock_cv_variant(
    request: Request,
    application_id: str,
    variant_key: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Lock the named CV variant: flip ``locked`` flags and copy its
    content into the canonical ``cv_html`` column.

    Returns the updated variants list and the new ``cv_html``.
    """
    user_id = current_user.get("id") or current_user.get("uid") or current_user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found")

    sb = get_supabase()

    app_resp = await asyncio.to_thread(
        lambda: sb.table(TABLES["applications"])
        .select("id,user_id,cv_html,cv_versions")
        .eq("id", application_id)
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )
    if not app_resp or not app_resp.data:
        raise HTTPException(status_code=404, detail="Application not found")

    app_data = app_resp.data
    variants_raw = app_data.get("cv_versions") or []
    if not isinstance(variants_raw, list) or not variants_raw:
        raise HTTPException(
            status_code=409,
            detail="Application has no CV variants to lock",
        )

    # Find target variant
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

    new_cv_html = target["content"]
    patch = {
        "cv_versions": new_variants,
        "cv_html": new_cv_html,
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
        "cv_variant.locked",
        application_id=application_id,
        variant=variant_key,
        user_id=user_id,
    )
    return {
        "applicationId": application_id,
        "lockedVariant": variant_key,
        "cvHtml": new_cv_html,
        "cvVariants": new_variants,
    }
