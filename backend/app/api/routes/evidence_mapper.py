"""
Evidence Mapper routes - Auto-map evidence to skill gaps (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

import structlog

from app.services.evidence_mapper import EvidenceMapperService
from app.api.deps import get_current_user
from app.core.security import limiter

logger = structlog.get_logger()

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class AutoMapRequest(BaseModel):
    gap_report_id: str = Field(..., min_length=1, max_length=100)
    application_id: Optional[str] = Field(None, max_length=100)

    @field_validator("gap_report_id")
    @classmethod
    def validate_gap_report_id(cls, v: str) -> str:
        try:
            _uuid.UUID(v)
        except (ValueError, AttributeError):
            raise ValueError("gap_report_id must be a valid UUID")
        return v


class ConfirmMappingRequest(BaseModel):
    confirmed: bool = True


@limiter.limit("10/minute")
@router.post("/auto-map")
async def auto_map_evidence(
    request: Request,
    body: AutoMapRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Auto-map all user evidence to gaps in a report."""
    service = EvidenceMapperService()
    try:
        return await service.auto_map(
            user_id=current_user["id"],
            gap_report_id=body.gap_report_id,
            application_id=body.application_id,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Evidence mapping failed. Please check your inputs.")
    except Exception:
        logger.error("evidence_mapping_failed", user_id=current_user["id"])
        raise HTTPException(status_code=500, detail="Evidence mapping failed. Please try again.")


@limiter.limit("30/minute")
@router.get("/mappings/{gap_report_id}")
async def get_mappings(
    request: Request,
    gap_report_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get all evidence mappings for a gap report."""
    _validate_uuid(gap_report_id, "gap_report_id")
    service = EvidenceMapperService()
    return await service.get_mappings(current_user["id"], gap_report_id)


@limiter.limit("30/minute")
@router.put("/mappings/{mapping_id}/confirm")
async def confirm_mapping(
    request: Request,
    mapping_id: str,
    body: ConfirmMappingRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Confirm or reject an AI-suggested mapping."""
    _validate_uuid(mapping_id, "mapping_id")
    service = EvidenceMapperService()
    success = await service.confirm_mapping(mapping_id, current_user["id"], body.confirmed)
    if not success:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"status": "updated", "confirmed": body.confirmed}
