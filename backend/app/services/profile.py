"""
Profile Service
Handles resume upload, parsing, and profile management with Firestore
"""
from typing import List, Optional, Dict, Any

from app.core.database import get_firestore_db, COLLECTIONS, FirestoreDB
from app.services.file_parser import FileParser
from ai_engine.client import AIClient
from ai_engine.chains.role_profiler import RoleProfilerChain


class ProfileService:
    """Service for profile operations."""

    def __init__(self, db: Optional[FirestoreDB] = None):
        self.db = db or get_firestore_db()
        self.file_parser = FileParser()
        self.ai_client = AIClient()

    async def create_from_upload(
        self,
        user_id: str,
        file_contents: bytes,
        file_name: str,
        file_type: str,
        is_primary: bool = False
    ) -> Dict[str, Any]:
        """Create a profile from uploaded resume file."""
        # Extract text from file
        raw_text = await self.file_parser.extract_text(file_contents, file_type)

        # Parse resume with AI
        profiler = RoleProfilerChain(self.ai_client)
        parsed_data = await profiler.parse_resume(raw_text)

        # If this is set as primary, unset other primary profiles
        if is_primary:
            existing_profiles = await self.get_user_profiles(user_id)
            for profile in existing_profiles:
                if profile.get('is_primary'):
                    await self.db.update(COLLECTIONS['profiles'], profile['id'], {'is_primary': False})

        # Check if user has any profiles
        has_profiles = await self._has_profiles(user_id)

        # Create profile data
        profile_data = {
            'user_id': user_id,
            'name': parsed_data.get('name'),
            'title': parsed_data.get('title'),
            'summary': parsed_data.get('summary'),
            'raw_resume_text': raw_text,
            'file_type': file_type,
            'parsed_data': parsed_data,
            'contact_info': parsed_data.get('contact_info'),
            'skills': parsed_data.get('skills', []),
            'experience': parsed_data.get('experience', []),
            'education': parsed_data.get('education', []),
            'certifications': parsed_data.get('certifications', []),
            'projects': parsed_data.get('projects', []),
            'languages': parsed_data.get('languages', []),
            'achievements': parsed_data.get('achievements', []),
            'is_primary': is_primary or not has_profiles
        }

        doc_id = await self.db.create(COLLECTIONS['profiles'], profile_data)
        return await self.db.get(COLLECTIONS['profiles'], doc_id)

    async def _has_profiles(self, user_id: str) -> bool:
        """Check if user has any profiles."""
        profiles = await self.db.query(
            COLLECTIONS['profiles'],
            filters=[('user_id', '==', user_id)],
            limit=1
        )
        return len(profiles) > 0

    async def get_user_profiles(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all profiles for a user."""
        return await self.db.query(
            COLLECTIONS['profiles'],
            filters=[('user_id', '==', user_id)],
            order_by='created_at',
            order_direction='DESCENDING'
        )

    async def get_primary_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user's primary profile."""
        profiles = await self.db.query(
            COLLECTIONS['profiles'],
            filters=[('user_id', '==', user_id), ('is_primary', '==', True)],
            limit=1
        )
        return profiles[0] if profiles else None

    async def get_profile(self, profile_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific profile."""
        profile = await self.db.get(COLLECTIONS['profiles'], profile_id)
        if profile and profile.get('user_id') == user_id:
            return profile
        return None

    async def update_profile(
        self,
        profile_id: str,
        user_id: str,
        update_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Update a profile."""
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return None

        await self.db.update(COLLECTIONS['profiles'], profile_id, update_data)
        return await self.db.get(COLLECTIONS['profiles'], profile_id)

    async def delete_profile(self, profile_id: str, user_id: str) -> bool:
        """Delete a profile."""
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return False

        await self.db.delete(COLLECTIONS['profiles'], profile_id)
        return True

    async def set_primary(self, profile_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Set a profile as primary."""
        # Unset all other primary profiles
        existing_profiles = await self.get_user_profiles(user_id)
        for profile in existing_profiles:
            if profile.get('is_primary'):
                await self.db.update(COLLECTIONS['profiles'], profile['id'], {'is_primary': False})

        # Set this profile as primary
        profile = await self.get_profile(profile_id, user_id)
        if not profile:
            return None

        await self.db.update(COLLECTIONS['profiles'], profile_id, {'is_primary': True})
        return await self.db.get(COLLECTIONS['profiles'], profile_id)

    async def reparse_profile(self, profile_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        """Re-parse a profile's resume with AI."""
        profile = await self.get_profile(profile_id, user_id)

        if not profile or not profile.get('raw_resume_text'):
            return None

        # Re-parse with AI
        profiler = RoleProfilerChain(self.ai_client)
        parsed_data = await profiler.parse_resume(profile['raw_resume_text'])

        # Update profile
        update_data = {
            'name': parsed_data.get('name'),
            'title': parsed_data.get('title'),
            'summary': parsed_data.get('summary'),
            'parsed_data': parsed_data,
            'contact_info': parsed_data.get('contact_info'),
            'skills': parsed_data.get('skills', []),
            'experience': parsed_data.get('experience', []),
            'education': parsed_data.get('education', []),
            'certifications': parsed_data.get('certifications', []),
            'projects': parsed_data.get('projects', []),
            'languages': parsed_data.get('languages', []),
            'achievements': parsed_data.get('achievements', []),
        }

        await self.db.update(COLLECTIONS['profiles'], profile_id, update_data)
        return await self.db.get(COLLECTIONS['profiles'], profile_id)
