"""
API Dependencies
Common dependencies for route handlers
"""
from typing import Optional, Dict, Any

from fastapi import Depends, HTTPException, status, Header

from app.core.database import verify_firebase_token, get_firestore_db, FirestoreDB, COLLECTIONS
from app.core.config import settings


async def get_token_from_header(
    authorization: str = Header(None)
) -> Optional[str]:
    """Extract token from Authorization header."""
    if authorization is None:
        return None
    if not authorization.startswith("Bearer "):
        return None
    return authorization.replace("Bearer ", "")


async def get_current_user(
    token: Optional[str] = Depends(get_token_from_header),
    db: FirestoreDB = Depends(get_firestore_db)
) -> Dict[str, Any]:
    """Get current authenticated user from Firebase token."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        # Verify token with Firebase
        decoded_token = verify_firebase_token(token)

        if not decoded_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        firebase_uid = decoded_token.get('uid')
        email = decoded_token.get('email')
        name = decoded_token.get('name') or decoded_token.get('display_name')
        picture = decoded_token.get('picture')

        # Get or create user in Firestore
        user = await db.get_or_create_user(
            firebase_uid=firebase_uid,
            email=email,
            full_name=name,
            avatar_url=picture
        )

        if not user.get('is_active', True):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is disabled"
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
    db: FirestoreDB = Depends(get_firestore_db)
) -> Optional[Dict[str, Any]]:
    """Get current user if authenticated, None otherwise."""
    if not token:
        return None
    try:
        return await get_current_user(token, db)
    except HTTPException:
        return None


async def require_premium_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Require premium subscription."""
    if not current_user.get('is_premium', False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Premium subscription required"
        )
    return current_user
