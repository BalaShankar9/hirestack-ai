"""
API Dependencies
Common dependencies for route handlers — Supabase JWT auth
"""
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Header

from app.core.database import verify_token_async, AuthServiceUnavailable, get_db, SupabaseDB
import uuid as _uuid


def validate_uuid(value: str, field_name: str = "id") -> str:
    """Validate that a string is a valid UUID. Raises 422 if not."""
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


async def get_token_from_header(
    authorization: str = Header(None),
) -> Optional[str]:
    """Extract token from Authorization header."""
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "")


DEV_USER: Dict[str, Any] = {
    "uid": "00000000-0000-0000-0000-000000000000",
    "id": "00000000-0000-0000-0000-000000000000",
    "email": "dev@hirestack.local",
    "full_name": "Dev User",
    "is_active": True,
}


async def get_current_user(
    token: Optional[str] = Depends(get_token_from_header),
    db: SupabaseDB = Depends(get_db),
) -> Dict[str, Any]:
    """Get current authenticated user from Supabase JWT."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        try:
            decoded_token = await verify_token_async(token, db=db)
        except AuthServiceUnavailable:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable. Please try again.",
            )

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


import structlog as _structlog  # noqa: E402
_billing_logger = _structlog.get_logger()


async def check_billing_limit(feature: str, current_user: Dict[str, Any]) -> None:
    """Check billing limit for a feature. Raises 402 if over limit.

    If the user has no org (testing/free solo mode), the check is skipped.
    """
    from app.services.org import OrgService
    from app.services.billing import BillingService

    org_service = OrgService()
    try:
        orgs = await org_service.get_user_orgs(current_user["id"])
    except Exception:
        orgs = []

    if not orgs:
        return  # No org — solo / testing mode, skip enforcement

    billing = BillingService()
    try:
        allowed = await billing.check_limit(orgs[0]["id"], feature)
    except Exception as exc:
        _billing_logger.warning("billing_check_failed", feature=feature, error=str(exc)[:200])
        return  # Fail-open on billing service errors

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Plan limit reached for {feature}. Please upgrade.",
        )
