"""B2.api — /api/tracked-companies CRUD route.

Authenticated CRUD over ``public.tracked_companies`` (migration
``20260507000000_tracked_companies.sql``). Validation/normalization is
delegated to the pure-fn ``tracked_companies_core.build_tracked_company``
so this route is a thin shell — auth + DB + 422-mapping.

Why so thin:
    The DB CHECK constraints are the truth. The pure-fn layer mirrors
    them so we can reject bad input fast, and the DB catches anything
    the pure-fn layer misses (defence in depth). The route's only job
    is wiring user_id + org_id from the auth context onto the row.

Hard rules:
    - List/get are user-scoped via ``filters=[("user_id", "==", uid)]``.
      RLS policy (``own_tracked_companies``) enforces the same scope at
      the DB; the explicit filter keeps queries cheap and predictable.
    - PATCH and DELETE re-fetch the row first to verify ownership BEFORE
      mutating. Belt + braces with RLS — this stops an `id` typo from
      surfacing a 500 instead of a 404.
    - PATCH never accepts ``provider`` / ``company_slug`` — those define
      the row's identity and the UNIQUE constraint, so changing them
      means "delete + create". Editable fields: display_name,
      careers_url, workday_tenant (workday only), enabled.
    - 422 mapping uses ``ValidationError.field`` + ``.reason`` so the UI
      can surface the offending field inline (no string parsing).
    - Rate limits: 30/min list/get (cheap), 10/min create/patch/delete
      (heavier writes, also bot-attractor).
"""

from __future__ import annotations

import logging
import uuid as _uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_user
from app.core.database import TABLES, SupabaseDB, get_db
from app.core.security import limiter
from app.services.tracked_companies_core import (
    PROVIDERS,
    TrackedCompanyInput,
    ValidationError,
    build_tracked_company,
    normalize_slug,
    normalize_workday_tenant,
    validate_provider,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def get_db_dep() -> SupabaseDB:
    """DI seam so tests can override with a fake DB.

    Mirrors the pattern used by ``batch_generate.commit_route`` —
    keeps the Supabase import lazy and overrideable.
    """
    return get_db()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name}: must be a valid UUID",
        )
    return value


def _map_validation_error(exc: ValidationError) -> HTTPException:
    """Translate the pure-fn ValidationError to an HTTP 422.

    The route is the right place to do this — keeping the core layer
    Pydantic-free means this is the only place that knows about
    HTTPException.
    """
    return HTTPException(
        status_code=422,
        detail={"field": exc.field, "reason": exc.reason},
    )


# ── Request schemas ─────────────────────────────────────────────────


class CreateTrackedCompanyRequest(BaseModel):
    """API request body for ``POST /api/tracked-companies``.

    Pydantic does *minimal* shape validation here — the real rules
    (slug regex, workday-iff-tenant, provider whitelist) live in the
    pure-fn core layer so they cross-import ``portal_scanner.PROVIDERS``
    and stay in sync with both the parser set and the DB CHECK.
    """

    provider: str
    company_slug: str
    display_name: str
    workday_tenant: Optional[str] = None
    careers_url: Optional[str] = None


class PatchTrackedCompanyRequest(BaseModel):
    """API request body for ``PATCH /api/tracked-companies/{id}``.

    Only the editable subset is allowed — ``provider`` and
    ``company_slug`` define the row's identity (UNIQUE constraint) so
    we don't expose a way to mutate them. ``enabled`` is the toggle the
    UI wires up to the on/off switch.
    """

    display_name: Optional[str] = None
    careers_url: Optional[str] = None
    workday_tenant: Optional[str] = None
    enabled: Optional[bool] = None


# ── Helpers ─────────────────────────────────────────────────────────


async def _get_owned_row_or_404(
    db: SupabaseDB, row_id: str, user_id: str
) -> Dict[str, Any]:
    """Fetch a tracked_companies row and verify ownership, or 404.

    Defence-in-depth alongside RLS: a leaked id from one user pointing
    at another user's row will return 404 rather than 500/403, which
    is the standard "don't leak existence" pattern.
    """
    row = await db.get(TABLES["tracked_companies"], row_id)
    if not row or row.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="Tracked company not found")
    return row


# ── Routes ──────────────────────────────────────────────────────────


@router.get("/tracked-companies")
@limiter.limit("30/minute")
async def list_tracked_companies(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    """List the caller's tracked companies (newest first).

    Returned shape mirrors the row directly — no projection — so the
    UI can render every column without a second round-trip. Sort by
    ``created_at DESC`` so a freshly-added company appears at the top
    of the list.
    """
    rows = await db.query(
        TABLES["tracked_companies"],
        filters=[("user_id", "==", current_user["id"])],
        order_by="created_at",
        order_direction="DESCENDING",
    )
    return {"items": rows, "count": len(rows)}


@router.post("/tracked-companies", status_code=201)
@limiter.limit("10/minute")
async def create_tracked_company(
    request: Request,
    body: CreateTrackedCompanyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    """Add a company to the caller's tracked list.

    422 on validation failure (mirrors DB CHECK). 409 on
    UNIQUE(user_id, provider, company_slug) collision so the UI can
    say "you're already tracking this".
    """
    try:
        _company, row = build_tracked_company(
            TrackedCompanyInput(
                provider=body.provider,
                company_slug=body.company_slug,
                display_name=body.display_name,
                workday_tenant=body.workday_tenant,
                careers_url=body.careers_url,
            )
        )
    except ValidationError as exc:
        raise _map_validation_error(exc)

    row["user_id"] = current_user["id"]
    org_id = current_user.get("org_id")
    if org_id:
        row["org_id"] = org_id

    try:
        new_id = await db.create(TABLES["tracked_companies"], row)
    except Exception as exc:
        # Supabase surfaces unique-violation as a wrapped error; we
        # check by string here because the underlying client doesn't
        # expose a typed exception. Same pattern used elsewhere in
        # the codebase.
        msg = str(exc).lower()
        if "duplicate" in msg or "unique" in msg or "23505" in msg:
            raise HTTPException(
                status_code=409,
                detail={
                    "field": "company_slug",
                    "reason": (
                        "you're already tracking this company on this "
                        "portal"
                    ),
                },
            )
        logger.exception("tracked_companies.create failed")
        raise

    created = await db.get(TABLES["tracked_companies"], new_id)
    return created or {"id": new_id, **row}


@router.patch("/tracked-companies/{row_id}")
@limiter.limit("10/minute")
async def patch_tracked_company(
    request: Request,
    row_id: str,
    body: PatchTrackedCompanyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, Any]:
    """Patch the editable subset of a tracked company.

    Re-applies the relevant pure-fn validators on a per-field basis
    rather than a full ``build_tracked_company`` so partial updates
    don't have to re-supply the immutable provider/slug pair.
    """
    existing = await _get_owned_row_or_404(db, row_id, current_user["id"])

    update: Dict[str, Any] = {}
    try:
        if body.display_name is not None:
            stripped = " ".join(body.display_name.split())
            if not stripped:
                raise ValidationError(
                    "display_name", "must not be empty"
                )
            if len(stripped) > 200:
                raise ValidationError(
                    "display_name", "must be ≤ 200 chars"
                )
            update["display_name"] = stripped

        if body.careers_url is not None:
            # Empty string → null (consistent with create-path coercion).
            cleaned = body.careers_url.strip() if body.careers_url else ""
            if cleaned == "":
                update["careers_url"] = None
            else:
                if not (
                    cleaned.startswith("http://")
                    or cleaned.startswith("https://")
                ):
                    raise ValidationError(
                        "careers_url",
                        "must start with http:// or https://",
                    )
                if len(cleaned) > 2048:
                    raise ValidationError(
                        "careers_url", "must be ≤ 2048 chars"
                    )
                update["careers_url"] = cleaned

        if body.workday_tenant is not None:
            # Re-validate against the EXISTING provider — patching
            # tenant on a non-workday row is the same DB CHECK
            # violation as on create.
            provider = validate_provider(existing["provider"])
            update["workday_tenant"] = normalize_workday_tenant(
                provider, body.workday_tenant
            )

        if body.enabled is not None:
            update["enabled"] = bool(body.enabled)
    except ValidationError as exc:
        raise _map_validation_error(exc)

    if not update:
        # No-op patch — return the row unchanged. Avoids an UPDATE
        # round-trip for an empty body.
        return existing

    ok = await db.update(TABLES["tracked_companies"], row_id, update)
    if not ok:
        raise HTTPException(
            status_code=500, detail="Failed to update tracked company"
        )

    refreshed = await db.get(TABLES["tracked_companies"], row_id)
    return refreshed or {**existing, **update}


@router.delete("/tracked-companies/{row_id}", status_code=200)
@limiter.limit("10/minute")
async def delete_tracked_company(
    request: Request,
    row_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db_dep),
) -> Dict[str, str]:
    """Remove a company from the caller's tracked list.

    Hard delete — the row carries no signal worth keeping after the
    user un-tracks. Scan history (separate table) is unaffected.
    """
    await _get_owned_row_or_404(db, row_id, current_user["id"])
    ok = await db.delete(TABLES["tracked_companies"], row_id)
    if not ok:
        raise HTTPException(
            status_code=500, detail="Failed to delete tracked company"
        )
    return {"status": "deleted", "id": row_id}
