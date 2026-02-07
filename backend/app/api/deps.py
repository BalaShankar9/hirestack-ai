"""
API Dependencies
Common dependencies for route handlers — Supabase JWT auth
"""
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Header

from app.core.database import verify_token, get_db, SupabaseDB, TABLES
from app.core.config import settings


async def get_token_from_header(
    authorization: str = Header(None),
) -> Optional[str]:
    """Extract token from Authorization header."""
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "")


async def get_current_user(
    token: Optional[str] = Depends(get_token_from_header),
    db: SupabaseDB = Depends(get_db),
) -> Dict[str, Any]:
    """Get current authenticated user from Supabase JWT."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        decoded_token = verify_token(token)

        if not decoded_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        uid = decoded_token.get("sub")
        email = decoded_token.get("email")
        meta = decoded_token.get("user_metadata", {})
        name = meta.get("full_name")
        picture = meta.get("avatar_url")

        user = await db.get_or_create_user(
            uid=uid,
            email=email,
            full_name=name,
            avatar_url=picture,
        )

        if not user.get("is_active", True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled",
            )

        return user

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_optional(
    token: Optional[str] = Depends(get_token_from_header),
    db: SupabaseDB = Depends(get_db),
) -> Optional[Dict[str, Any]]:
    """Get current user if authenticated, None otherwise."""
    if not token:
        return None
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None


async def require_premium_user(
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> Dict[str, Any]:
    """Require premium subscription."""
    if not current_user.get("is_premium", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required",
        )
    return current_user
