"""
Authentication Service
Handles user authentication via Supabase Auth.
Supabase Auth handles login/registration on the frontend.
This service manages user data in PostgreSQL via PostgREST.
"""
from typing import Optional, Dict, Any

from app.core.database import verify_token, get_db, TABLES, SupabaseDB


class AuthService:
    """Service for handling authentication operations."""

    def __init__(self, db: Optional[SupabaseDB] = None):
        self.db = db or get_db()

    async def get_or_create_user(
        self,
        uid: str,
        email: str,
        full_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        # Keep old kwarg name working for callers that still pass firebase_uid=
        firebase_uid: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get existing user or create new one from Supabase auth data."""
        effective_uid = uid or firebase_uid
        return await self.db.get_or_create_user(
            uid=effective_uid,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
        )

    async def get_user_by_auth_uid(self, uid: str) -> Optional[Dict[str, Any]]:
        """Get user by Supabase Auth UID."""
        return await self.db.get_user_by_auth_uid(uid)

    # Backward-compat alias
    async def get_user_by_firebase_uid(self, firebase_uid: str) -> Optional[Dict[str, Any]]:
        return await self.get_user_by_auth_uid(firebase_uid)

    async def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by internal ID."""
        return await self.db.get(TABLES['users'], user_id)

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
            await self.db.update(TABLES['users'], user_id, update_data)

        return await self.db.get(TABLES['users'], user_id)

    async def deactivate_user(self, user_id: str) -> None:
        """Deactivate a user account."""
        await self.db.update(TABLES['users'], user_id, {'is_active': False})

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Verify Supabase access token."""
        return verify_token(token)
