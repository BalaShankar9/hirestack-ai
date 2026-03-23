"""
Document Variant routes - A/B Doc Lab (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.doc_variant import DocVariantService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class GenerateVariantsRequest(BaseModel):
    original_content: str = Field(..., max_length=100_000)
    document_type: str = Field(..., max_length=50)
    job_title: str = Field("", max_length=300)
    company: str = Field("", max_length=300)
    application_id: Optional[str] = None
    tones: Optional[List[str]] = None


@router.post("/generate")
@limiter.limit("5/minute")
async def generate_variants(
    request: Request,
    body: GenerateVariantsRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate multiple tone variants of a document."""
    service = DocVariantService()
    try:
        return await service.generate_variants(
            user_id=current_user["id"],
            original_content=body.original_content,
            document_type=body.document_type,
            job_title=body.job_title,
            company=body.company,
            application_id=body.application_id,
            tones=body.tones,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Variant generation failed. Please try again.")


@router.get("/")
@limiter.limit("30/minute")
async def get_variants(
    request: Request,
    application_id: Optional[str] = None,
    document_type: Optional[str] = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get variants for the current user."""
    service = DocVariantService()
    return await service.get_variants(current_user["id"], application_id, document_type)


@router.put("/{variant_id}/select")
@limiter.limit("20/minute")
async def select_variant(
    request: Request,
    variant_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Select a variant as the chosen one."""
    _validate_uuid(variant_id, "variant_id")
    service = DocVariantService()
    success = await service.select_variant(variant_id, current_user["id"])
    if not success:
        raise HTTPException(status_code=404, detail="Variant not found")
    return {"status": "selected", "variant_id": variant_id}
