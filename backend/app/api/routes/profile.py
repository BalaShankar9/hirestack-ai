"""
Profile routes - Resume upload, parsing, career intelligence, and universal documents
"""
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from pydantic import BaseModel

from app.services.profile import ProfileService
from app.api.deps import get_current_user
import structlog

logger = structlog.get_logger()

router = APIRouter()


class SocialLinksUpdate(BaseModel):
    linkedin: str = ""
    github: str = ""
    website: str = ""
    twitter: str = ""
    other: str = ""


# ── Upload & CRUD ──────────────────────────────────────────────────────


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
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        error_msg = str(e)
        logger.error("upload_resume_failed", error=error_msg, endpoint="upload_resume", user_id=current_user["id"])

        # Surface actionable error messages instead of generic ones
        if "api key" in error_msg.lower() or "not configured" in error_msg.lower():
            detail = "AI service is not configured. Please contact support."
        elif "quota" in error_msg.lower() or "rate limit" in error_msg.lower() or "resource_exhausted" in error_msg.lower():
            detail = "AI service is temporarily busy. Please try again in a moment."
        elif "timeout" in error_msg.lower() or "timed out" in error_msg.lower():
            detail = "Resume parsing timed out. Please try again or upload a smaller file."
        elif "parse json" in error_msg.lower() or "json" in error_msg.lower():
            detail = "Failed to parse resume content. Please try uploading a different format."
        else:
            detail = f"Resume parsing failed: {error_msg[:200]}"

        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


@router.get("")
async def list_profiles(current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all user's profiles."""
    service = ProfileService()
    return await service.get_user_profiles(current_user["id"])


@router.get("/primary")
async def get_primary_profile(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user's primary profile."""
    service = ProfileService()
    profile = await service.get_primary_profile(current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No primary profile found. Please upload a resume.")
    return profile


@router.get("/{profile_id}")
async def get_profile(profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get a specific profile."""
    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.put("/{profile_id}")
async def update_profile(profile_id: str, profile_data: Dict[str, Any], current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update a profile."""
    service = ProfileService()
    profile = await service.update_profile(profile_id=profile_id, user_id=current_user["id"], update_data=profile_data)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a profile."""
    service = ProfileService()
    deleted = await service.delete_profile(profile_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")


@router.post("/{profile_id}/set-primary")
async def set_primary_profile(profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Set a profile as the primary profile."""
    service = ProfileService()
    profile = await service.set_primary(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@router.post("/{profile_id}/reparse")
async def reparse_profile(profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Re-parse a profile's resume with AI."""
    service = ProfileService()
    profile = await service.reparse_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


# ── Career Intelligence ────────────────────────────────────────────────


@router.get("/intelligence/completeness")
async def get_completeness(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get profile completeness score."""
    service = ProfileService()
    profile = await service.get_primary_profile(current_user["id"])
    if not profile:
        return {"score": 0, "sections": {}, "suggestions": ["Upload your resume to get started"]}
    return service.compute_completeness(profile)


@router.get("/intelligence/resume-worth")
async def get_resume_worth(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get resume worth score."""
    service = ProfileService()
    return await service.compute_resume_worth(current_user["id"])


@router.get("/intelligence/aggregate-gaps")
async def get_aggregate_gaps(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get aggregate gap analysis across all applications."""
    service = ProfileService()
    return await service.aggregate_gap_analysis(current_user["id"])


@router.get("/intelligence/market")
async def get_market_intelligence(
    force_refresh: bool = False,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get market intelligence based on user's location and skills."""
    service = ProfileService()
    try:
        return await service.compute_market_intelligence(current_user["id"], force_refresh=force_refresh)
    except Exception as e:
        logger.error("market_intelligence_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Market analysis failed")


# ── Universal Documents ────────────────────────────────────────────────


@router.post("/{profile_id}/augment-skills")
async def augment_skills(profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Augment profile skills from connected platforms (GitHub, etc.)."""
    service = ProfileService()
    result = await service.augment_skills_from_connections(profile_id, current_user["id"])
    return result


@router.post("/{profile_id}/universal-documents")
async def generate_universal_documents(profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Generate universal documents (resume, CV, personal statement, portfolio) from profile."""
    service = ProfileService()
    try:
        docs = await service.generate_universal_documents(profile_id, current_user["id"])
        return docs
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("universal_doc_generation_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Document generation failed")


# ── Social Links ───────────────────────────────────────────────────────


@router.put("/{profile_id}/social-links")
async def update_social_links(profile_id: str, links: SocialLinksUpdate, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update social links for a profile."""
    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    links_dict = links.model_dump()

    # Always store URLs in contact_info (column that exists in DB)
    contact_info = profile.get("contact_info") or {}
    for key in ("linkedin", "github", "website", "twitter"):
        if links_dict.get(key):
            contact_info[key] = links_dict[key]
    # Preserve existing social_connections data
    update_data: Dict[str, Any] = {"contact_info": contact_info}

    # Also try social_links column if it exists
    update_data["social_links"] = links_dict

    updated = await service.update_profile(
        profile_id=profile_id,
        user_id=current_user["id"],
        update_data=update_data,
    )
    return updated


# ── Social Profile Connector ──────────────────────────────────────────


class ConnectSocialRequest(BaseModel):
    platform: str  # "github" | "linkedin" | "website" | "twitter"
    url: str


@router.post("/{profile_id}/connect-social")
async def connect_social(
    profile_id: str,
    req: ConnectSocialRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Connect an external profile and extract data."""
    valid_platforms = {"github", "linkedin", "website", "twitter"}
    if req.platform not in valid_platforms:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid platform. Must be one of: {', '.join(valid_platforms)}",
        )

    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    from app.services.social_connector import SocialConnector

    connector = SocialConnector()
    try:
        # Pass profile data for LinkedIn AI analysis
        profile_data = profile if req.platform == "linkedin" else None
        result = await connector.connect(req.platform, req.url, profile_data=profile_data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("social_connect_error", platform=req.platform, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to connect to profile. Please try again.",
        )

    connection_entry = {"url": req.url, **result}

    # Store in contact_info.social_connections (always exists in DB)
    contact_info = profile.get("contact_info") or {}
    social_connections = contact_info.get("social_connections") or {}
    social_connections[req.platform] = connection_entry
    contact_info["social_connections"] = social_connections
    # Also store the URL in the standard contact_info field
    if req.platform in ("linkedin", "github", "website"):
        contact_info[req.platform] = req.url

    update_data: Dict[str, Any] = {"contact_info": contact_info}
    # Also try social_links if column exists (best-effort)
    try:
        social_links = profile.get("social_links") or {}
        if isinstance(social_links.get(req.platform), str):
            social_links[req.platform] = {"url": social_links[req.platform]}
        social_links[req.platform] = connection_entry
        update_data["social_links"] = social_links
    except Exception:
        pass

    await service.update_profile(
        profile_id=profile_id,
        user_id=current_user["id"],
        update_data=update_data,
    )

    # Auto-augment skills after GitHub connect
    augment_result = None
    if req.platform == "github" and result.get("status") == "connected":
        try:
            augment_result = await service.augment_skills_from_connections(profile_id, current_user["id"])
            logger.info("auto_augment_skills", added=augment_result.get("added", 0))
        except Exception as e:
            logger.warning("auto_augment_skills_failed", error=str(e)[:200])

    response = {"platform": req.platform, "url": req.url, **result}
    if augment_result:
        response["skills_augmented"] = augment_result.get("added", 0)
    return response


# ── Evidence Sync ──────────────────────────────────────────────────────


@router.get("/evidence/synced")
async def get_synced_evidence(current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get evidence vault items synced to profile."""
    service = ProfileService()
    return await service.get_synced_evidence(current_user["id"])
