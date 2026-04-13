"""
Profile routes - Resume upload, parsing, career intelligence, and universal documents
"""
from typing import Dict, Any, Optional

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from pydantic import BaseModel, Field

from app.services.profile import ProfileService
from app.api.deps import get_current_user, validate_uuid
import structlog

logger = structlog.get_logger()


class UpdateProfileRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=500)
    title: Optional[str] = Field(None, max_length=500)
    summary: Optional[str] = Field(None, max_length=10000)
    contact_info: Optional[Dict[str, Any]] = None
    skills: Optional[list] = None
    experience: Optional[list] = None
    education: Optional[list] = None
    certifications: Optional[list] = None
    projects: Optional[list] = None
    languages: Optional[list] = None
    achievements: Optional[list] = None
    social_links: Optional[Dict[str, Any]] = None
    is_primary: Optional[bool] = None

router = APIRouter()


class SocialLinksUpdate(BaseModel):
    linkedin: str = ""
    github: str = ""
    website: str = ""
    twitter: str = ""
    other: str = ""


# ── Upload & CRUD ──────────────────────────────────────────────────────


@limiter.limit("5/minute")
@router.post("/upload")
async def upload_resume(
    request: Request,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Upload and parse a resume file."""
    allowed_types = [".pdf", ".docx", ".doc", ".txt"]
    file_ext = "." + file.filename.split(".")[-1].lower() if file.filename and "." in file.filename else ""

    if not file_ext or file_ext not in allowed_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_types)}",
        )

    contents = await file.read()
    if not contents or len(contents) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")
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
        from app.core.database import cache_invalidate_prefix
        await cache_invalidate_prefix(f"profiles:{current_user['id']}")
        await cache_invalidate_prefix(f"profiles:list:{current_user['id']}")
        await cache_invalidate_prefix(f"profiles:primary:{current_user['id']}")
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


@limiter.limit("30/minute")
@router.get("/all")
@router.get("")
async def list_profiles(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """List all user's profiles."""
    from app.core.database import cache_get, cache_set
    cache_key = f"profiles:list:{current_user['id']}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    service = ProfileService()
    result = await service.get_user_profiles(current_user["id"])
    await cache_set(cache_key, result, ttl=120)
    return result


@limiter.limit("30/minute")
@router.get("/primary")
async def get_primary_profile(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get user's primary profile."""
    from app.core.database import cache_get, cache_set
    cache_key = f"profiles:primary:{current_user['id']}"
    cached = await cache_get(cache_key)
    if cached is not None:
        return cached
    service = ProfileService()
    profile = await service.get_primary_profile(current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No primary profile found. Please upload a resume.")
    await cache_set(cache_key, profile, ttl=120)
    return profile


@limiter.limit("30/minute")
@router.get("/{profile_id}")
async def get_profile(
    request: Request,
    profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get a specific profile."""
    validate_uuid(profile_id, "profile_id")
    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


@limiter.limit("30/minute")
@router.put("/{profile_id}")
async def update_profile(
    request: Request,
    profile_id: str, profile_data: UpdateProfileRequest, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update a profile."""
    service = ProfileService()
    profile = await service.update_profile(profile_id=profile_id, user_id=current_user["id"], update_data=profile_data.model_dump(exclude_none=True))
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    from app.core.database import cache_invalidate_prefix
    await cache_invalidate_prefix(f"profiles:{current_user['id']}")
    await cache_invalidate_prefix(f"profiles:list:{current_user['id']}")
    await cache_invalidate_prefix(f"profiles:primary:{current_user['id']}")
    return profile


@limiter.limit("30/minute")
@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_profile(
    request: Request,
    profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Delete a profile."""
    service = ProfileService()
    deleted = await service.delete_profile(profile_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    from app.core.database import cache_invalidate_prefix
    await cache_invalidate_prefix(f"profiles:{current_user['id']}")
    await cache_invalidate_prefix(f"profiles:list:{current_user['id']}")
    await cache_invalidate_prefix(f"profiles:primary:{current_user['id']}")


@limiter.limit("30/minute")
@router.post("/{profile_id}/set-primary")
async def set_primary_profile(
    request: Request,
    profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Set a profile as the primary profile."""
    service = ProfileService()
    profile = await service.set_primary(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    from app.core.database import cache_invalidate_prefix
    await cache_invalidate_prefix(f"profiles:{current_user['id']}")
    await cache_invalidate_prefix(f"profiles:list:{current_user['id']}")
    await cache_invalidate_prefix(f"profiles:primary:{current_user['id']}")
    return profile


@limiter.limit("5/minute")
@router.post("/{profile_id}/reparse")
async def reparse_profile(
    request: Request,
    profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Re-parse a profile's resume with AI."""
    service = ProfileService()
    profile = await service.reparse_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return profile


# ── Career Intelligence ────────────────────────────────────────────────


@limiter.limit("30/minute")
@router.get("/intelligence/completeness")
async def get_completeness(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get profile completeness score."""
    service = ProfileService()
    profile = await service.get_primary_profile(current_user["id"])
    if not profile:
        return {"score": 0, "sections": {}, "suggestions": ["Upload your resume to get started"]}
    return service.compute_completeness(profile)


@limiter.limit("5/minute")
@router.get("/intelligence/resume-worth")
async def get_resume_worth(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get resume worth score."""
    service = ProfileService()
    return await service.compute_resume_worth(current_user["id"])


@limiter.limit("30/minute")
@router.get("/intelligence/aggregate-gaps")
async def get_aggregate_gaps(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get aggregate gap analysis across all applications."""
    service = ProfileService()
    return await service.aggregate_gap_analysis(current_user["id"])


@limiter.limit("5/minute")
@router.get("/intelligence/market")
async def get_market_intelligence(
    request: Request,
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


@limiter.limit("5/minute")
@router.post("/{profile_id}/augment-skills")
async def augment_skills(
    request: Request,
    profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Augment profile skills from connected platforms (GitHub, etc.)."""
    service = ProfileService()
    result = await service.augment_skills_from_connections(profile_id, current_user["id"])
    return result


@limiter.limit("5/minute")
@router.post("/{profile_id}/universal-documents")
async def generate_universal_documents(
    request: Request,
    profile_id: str, current_user: Dict[str, Any] = Depends(get_current_user)):
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


@limiter.limit("30/minute")
@router.put("/{profile_id}/social-links")
async def update_social_links(
    request: Request,
    profile_id: str, links: SocialLinksUpdate, current_user: Dict[str, Any] = Depends(get_current_user)):
    """Update social links for a profile."""
    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")

    links_dict = links.model_dump()

    # Build canonical social_links: preserve existing connection data, update URLs
    existing_social = profile.get("social_links") or {}
    new_social: Dict[str, Any] = {}
    for key in ("linkedin", "github", "website", "twitter"):
        url = links_dict.get(key, "")
        existing = existing_social.get(key)
        if isinstance(existing, dict):
            # Preserve connection data, update URL
            new_social[key] = {**existing, "url": url}
        elif url:
            new_social[key] = {"url": url, "status": "linked"}
        else:
            new_social[key] = {"url": "", "status": "none"}
    if links_dict.get("other"):
        new_social["other"] = links_dict["other"]

    # Mirror plain URLs into contact_info for backward compat
    contact_info = profile.get("contact_info") or {}
    for key in ("linkedin", "github", "website", "twitter"):
        if links_dict.get(key):
            contact_info[key] = links_dict[key]

    update_data: Dict[str, Any] = {
        "social_links": new_social,
        "contact_info": contact_info,
    }

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


@limiter.limit("5/minute")
@router.post("/{profile_id}/connect-social")
async def connect_social(
    request: Request,
    profile_id: str,
    req: ConnectSocialRequest,
    current_user: Dict[str, Any] = Depends(get_current_user
),
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

    # Build unified social_links entry: url + status + data + timestamp
    connection_entry = {
        "url": req.url,
        "status": result.get("status", "connected"),
        "connected_at": result.get("connected_at"),
        "data": result.get("data"),
    }

    # Update social_links (canonical source)
    social_links = profile.get("social_links") or {}
    social_links[req.platform] = connection_entry

    # Mirror plain URL into contact_info for backward compat
    contact_info = profile.get("contact_info") or {}
    if req.platform in ("linkedin", "github", "website"):
        contact_info[req.platform] = req.url
    # Keep legacy social_connections for any code that reads it
    social_connections = contact_info.get("social_connections") or {}
    social_connections[req.platform] = {"url": req.url, **result}
    contact_info["social_connections"] = social_connections

    update_data: Dict[str, Any] = {
        "social_links": social_links,
        "contact_info": contact_info,
    }

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


@limiter.limit("30/minute")
@router.get("/evidence/synced")
async def get_synced_evidence(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Get evidence vault items synced to profile."""
    service = ProfileService()
    return await service.get_synced_evidence(current_user["id"])


@limiter.limit("10/minute")
@router.post("/{profile_id}/sync-evidence")
async def sync_evidence(
    request: Request,
    profile_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user)):
    """Merge evidence vault items into profile data."""
    service = ProfileService()
    profile = await service.get_profile(profile_id, current_user["id"])
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
    return await service.sync_evidence_to_profile(profile_id, current_user["id"])
