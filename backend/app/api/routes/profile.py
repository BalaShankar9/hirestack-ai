"""
Profile routes - Resume upload and parsing (Firestore)
"""
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form

from app.services.profile import ProfileService
from app.api.deps import get_current_user

router = APIRouter()


@router.post("/upload")
async def upload_resume(
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Upload and parse a resume file."""
    allowed_types = [".pdf", ".docx", ".doc", ".txt"]
    file_ext = "." + file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ""

    if file_ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_types)}",
        )

    contents = await file.read()
    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File too large. Maximum size is 10MB")

    service = ProfileService()
    try:
        profile = await service.create_from_upload(
            user_id=current_user["id"],
            file_contents=contents,
            file_name=file.filename,
            file_type=file_ext,
            is_primary=is_primary,
        )
        return profile
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to process resume: {e}")


@router.get("")
async def list_profiles(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's profiles."""
    service = ProfileService()
    return await service.get_user_profiles(current_user["id"])


@router.get("/primary")
async def get_primary_profile(
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get user's primary profile."""
    service = ProfileService()
    profile = await service.get_primary_profile(current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No primary profile found. Please upload a resume.")
    return profile


@router.get("/{profile_id}")
async def get_profile(
    profile_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific profile."""
    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.put("/{profile_id}")
async def update_profile(
    profile_id: str,
    profile_data: Dict[str, Any],
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a profile."""
    service = ProfileService()
    profile = await service.update_profile(profile_id=profile_id, user_id=current_user["id"], update_data=profile_data)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    profile_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a profile."""
    service = ProfileService()
    deleted = await service.delete_profile(profile_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.post("/{profile_id}/set-primary")
async def set_primary_profile(
    profile_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Set a profile as the primary profile."""
    service = ProfileService()
    profile = await service.set_primary(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.post("/{profile_id}/reparse")
async def reparse_profile(
    profile_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Re-parse a profile's resume with AI."""
    service = ProfileService()
    profile = await service.reparse_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile
