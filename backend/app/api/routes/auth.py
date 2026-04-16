"""
Authentication routes — Supabase JWT auth.
Supabase handles registration/login on the frontend.
The backend verifies Supabase JWTs.
"""
from typing import Optional, Dict, Any

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Header, Request

from app.core.database import verify_token_async, AuthServiceUnavailable, get_db, SupabaseDB, TABLES
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/verify")
@limiter.limit("10/minute")
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

    meta = decoded_token.get("user_metadata", {})
    return {
        "valid": True,
        "uid": decoded_token.get("sub"),
        "email": decoded_token.get("email"),
        "name": meta.get("full_name"),
    }


@router.get("/me")
@limiter.limit("10/minute")
async def get_current_user_info(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get current authenticated user."""
    return current_user


@router.put("/me")
@limiter.limit("10/minute")
async def update_current_user(
    request: Request,
    full_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
):
    """Update current user's profile."""
    update_data = {}
    if full_name is not None:
        update_data["full_name"] = full_name
    if avatar_url is not None:
        update_data["avatar_url"] = avatar_url

    if update_data:
        await db.update(TABLES["users"], current_user["id"], update_data)
        updated_user = await db.get(TABLES["users"], current_user["id"])
        return updated_user

    return current_user


@router.post("/sync")
@limiter.limit("10/minute")
async def sync_user(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Sync user data. Called after frontend login."""
    return {
        "message": "User synced successfully",
        "user_id": current_user.get("id"),
        "email": current_user.get("email"),
    }
