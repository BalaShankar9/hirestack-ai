"""
Authentication Service
Handles user authentication with Firebase
Note: Firebase handles login/registration on the frontend.
This service manages user data in Firestore.
"""
from typing import Optional, Dict, Any

from app.core.database import verify_firebase_token, get_firestore_db, COLLECTIONS, FirestoreDB


class AuthService:
    """Service for handling authentication operations."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()

    async def get_or_create_user(
        self,
        firebase_uid: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get existing user or create new one from Firebase auth data."""
        return await self.db.get_or_create_user(
            firebase_uid=firebase_uid,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url
        )

    async def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        """Get user by Firebase UID."""
        return await self.db.get_user_by_firebase_uid(firebase_uid)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by internal ID."""
        return await self.db.get(COLLECTIONS['users'], user_id)

    async def update_user(
        self,
        user_id: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update user profile."""
        update_data = {}
        if full_name is not None:
            update_data['full_name'] = full_name
        if avatar_url is not None:
            update_data['avatar_url'] = avatar_url

        if update_data:
            await self.db.update(COLLECTIONS['users'], user_id, update_data)

        return await self.db.get(COLLECTIONS['users'], user_id)

    async def deactivate_user(self, user_id: str) -> None:
        """Deactivate a user account."""
        await self.db.update(COLLECTIONS['users'], user_id, {'is_active': False})

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify Firebase ID token."""
        return verify_firebase_token(token)
