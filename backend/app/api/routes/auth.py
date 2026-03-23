"""
Authentication routes — Supabase JWT auth.
Supabase handles registration/login on the frontend.
The backend verifies Supabase JWTs.
"""
from typing import Optional, Dict, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status, Header
from pydantic import BaseModel, Field, HttpUrl

from app.core.database import verify_token_async, AuthServiceUnavailable, get_db, SupabaseDB, TABLES
from app.core.security import limiter, MAX_TOKEN_SIZE
from app.api.deps import get_current_user

logger = structlog.get_logger()
router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class UpdateProfileBody(BaseModel):
    """Body for PUT /me — uses JSON body instead of query params."""
    full_name: Optional[str] = Field(None, max_length=200)
    avatar_url: Optional[str] = Field(None, max_length=2048)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/verify")
@limiter.limit("30/minute")
async def verify_token_endpoint(
    request: Request,
    authorization: str = Header(...),
):
    """Verify Supabase JWT and return user info."""
    token = authorization.replace("Bearer ", "") if authorization else None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided",
        )

    if len(token) > MAX_TOKEN_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token too large",
        )

    try:
        decoded_token = await verify_token_async(token)
    except AuthServiceUnavailable:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable. Please try again.",
        )

    if not decoded_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    uid = decoded_token.get("sub")
    if not uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token: missing user ID",
        )

    meta = decoded_token.get("user_metadata", {})
    return {
        "valid": True,
        "uid": uid,
        "email": decoded_token.get("email"),
        "name": meta.get("full_name"),
    }


@router.get("/me")
@limiter.limit("60/minute")
async def get_current_user_info(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get current authenticated user."""
    return current_user


@router.put("/me")
@limiter.limit("20/minute")
async def update_current_user(
    request: Request,
    body: UpdateProfileBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
):
    """Update current user's profile."""
    update_data = {}
    if body.full_name is not None:
        update_data["full_name"] = body.full_name
    if body.avatar_url is not None:
        update_data["avatar_url"] = body.avatar_url

    if update_data:
        await db.update(TABLES["users"], current_user["id"], update_data)
        updated_user = await db.get(TABLES["users"], current_user["id"])

        logger.info("user_profile_updated",
                     user_id=current_user["id"],
                     fields=list(update_data.keys()))
        return updated_user

    return current_user


@router.post("/sync")
@limiter.limit("20/minute")
async def sync_user(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
):
    """Sync user data. Called after frontend login. Logs the sign‑in event."""
    # Log auth event for audit trail
    try:
        await db.create(TABLES["auth_events"], {
            "user_id": current_user.get("id"),
            "event_type": "login",
            "ip_address": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
            "metadata": {"source": "sync_endpoint"},
        })
    except Exception as e:
        logger.warning("audit_log_failed", error=str(e))

    return {
        "message": "User synced successfully",
        "user_id": current_user.get("id"),
        "email": current_user.get("email"),
    }
