"""
White-Label API routes - API key management and usage tracking (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.api_keys import APIKeyService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class CreateKeyRequest(BaseModel):
    name: str = Field("Default Key", max_length=200)
    scopes: Optional[List[str]] = None
    rate_limit: int = Field(100, ge=1, le=10000)
    expires_days: Optional[int] = Field(None, ge=1, le=365)


@limiter.limit("10/minute")
@router.post("/keys")
async def create_api_key(
    http_request: Request,
    request: CreateKeyRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new API key. The raw key is only returned once."""
    service = APIKeyService()
    return await service.create_key(
        user_id=current_user["id"],
        name=request.name,
        scopes=request.scopes,
        rate_limit=request.rate_limit,
        expires_days=request.expires_days,
    )


@limiter.limit("30/minute")
@router.get("/keys")
async def get_api_keys(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get all API keys for the current user."""
    service = APIKeyService()
    return await service.get_keys(current_user["id"])


@limiter.limit("20/minute")
@router.delete("/keys/{key_id}")
async def revoke_api_key(
    request: Request,
    key_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Revoke an API key."""
    _validate_uuid(key_id, "key_id")
    service = APIKeyService()
    success = await service.revoke_key(key_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="API key not found")
    return {"status": "revoked"}


@limiter.limit("30/minute")
@router.get("/usage")
async def get_usage_stats(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get API usage statistics."""
    service = APIKeyService()
    return await service.get_usage_stats(current_user["id"], days)
