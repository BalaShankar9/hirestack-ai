"""
Profile routes - Resume upload and parsing
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.user import UserResponse
from app.schemas.profile import (
    ProfileCreate, ProfileUpdate, ProfileResponse, ParsedProfile
)
from app.services.profile import ProfileService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/upload", response_model=ProfileResponse)
async def upload_resume(
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Upload and parse a resume file."""
    # Validate file type
    allowed_types = [".pdf", ".docx", ".doc", ".txt"]
    file_ext = "." + file.filename.split(".")[-1].lower() if "." in file.filename else ""

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_types)}"
        )

    # Validate file size (10MB max)
    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File too large. Maximum size is 10MB"
        )

    profile_service = ProfileService(db)
    try:
        profile = await profile_service.create_from_upload(
            user_id=current_user.id,
            file_contents=contents,
            file_name=file.filename,
            file_type=file_ext,
            is_primary=is_primary
        )
        return profile
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process resume: {str(e)}"
        )


@router.get("", response_model=List[ProfileResponse])
async def list_profiles(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List all user's profiles."""
    profile_service = ProfileService(db)
    profiles = await profile_service.get_user_profiles(current_user.id)
    return profiles


@router.get("/primary", response_model=ProfileResponse)
async def get_primary_profile(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get user's primary profile."""
    profile_service = ProfileService(db)
    profile = await profile_service.get_primary_profile(current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No primary profile found. Please upload a resume."
        )
    return profile


@router.get("/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a specific profile."""
    profile_service = ProfileService(db)
    profile = await profile_service.get_profile(profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile


@router.put("/{profile_id}", response_model=ProfileResponse)
async def update_profile(
    profile_id: UUID,
    profile_data: ProfileUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a profile."""
    profile_service = ProfileService(db)
    profile = await profile_service.update_profile(
        profile_id=profile_id,
        user_id=current_user.id,
        update_data=profile_data
    )
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a profile."""
    profile_service = ProfileService(db)
    deleted = await profile_service.delete_profile(profile_id, current_user.id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )


@router.post("/{profile_id}/set-primary", response_model=ProfileResponse)
async def set_primary_profile(
    profile_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Set a profile as the primary profile."""
    profile_service = ProfileService(db)
    profile = await profile_service.set_primary(profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile


@router.post("/{profile_id}/reparse", response_model=ProfileResponse)
async def reparse_profile(
    profile_id: UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Re-parse a profile's resume with AI."""
    profile_service = ProfileService(db)
    profile = await profile_service.reparse_profile(profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found"
        )
    return profile
