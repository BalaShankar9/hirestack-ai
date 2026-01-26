"""
Authentication routes using Firebase Auth
Note: Firebase handles registration/login on the frontend.
The backend verifies Firebase ID tokens.
"""
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Header

from app.core.database import verify_firebase_token, get_firestore_db, FirestoreDB, COLLECTIONS
from app.api.deps import get_current_user

router = APIRouter()


@router.get("/verify")
async def verify_token(
    authorization: str = Header(...),
):
    """Verify Firebase ID token and return user info."""
    token = authorization.replace("Bearer ", "") if authorization else None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided"
        )

    decoded_token = verify_firebase_token(token)

    if not decoded_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return {
        "valid": True,
        "uid": decoded_token.get('uid'),
        "email": decoded_token.get('email'),
        "name": decoded_token.get('name'),
    }


@router.get("/me")
async def get_current_user_info(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Get current authenticated user."""
    return current_user


@router.put("/me")
async def update_current_user(
    full_name: Optional[str] = None,
    avatar_url: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: FirestoreDB = Depends(get_firestore_db)
):
    """Update current user's profile."""
    update_data = {}
    if full_name is not None:
        update_data['full_name'] = full_name
    if avatar_url is not None:
        update_data['avatar_url'] = avatar_url

    if update_data:
        await db.update(COLLECTIONS['users'], current_user['id'], update_data)
        updated_user = await db.get(COLLECTIONS['users'], current_user['id'])
        return updated_user

    return current_user


@router.post("/sync")
async def sync_user(
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """Sync Firebase user data to Firestore. Called after frontend login."""
    return {
        "message": "User synced successfully",
        "user_id": current_user.get('id'),
        "email": current_user.get('email')
    }
