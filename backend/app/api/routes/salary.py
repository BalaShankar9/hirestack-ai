"""
Salary Coach routes - Salary analysis and negotiation coaching (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.services.salary import SalaryService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()


def _validate_uuid(value: str, field_name: str = "id") -> str:
    try:
        _uuid.UUID(value)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=422, detail=f"Invalid {field_name}: must be a valid UUID")
    return value


class SalaryAnalysisRequest(BaseModel):
    job_title: str = Field(..., max_length=300)
    company: str = Field("", max_length=300)
    location: str = Field("", max_length=300)
    experience_years: float = Field(0, ge=0, le=70)
    current_salary: float = Field(0, ge=0)
    skills_summary: str = Field("", max_length=10_000)
    application_id: Optional[str] = None


@router.post("/analyze")
@limiter.limit("5/minute")
async def analyze_salary(
    request: Request,
    body: SalaryAnalysisRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a comprehensive salary analysis with negotiation scripts."""
    service = SalaryService()
    try:
        return await service.analyze(
            user_id=current_user["id"],
            job_title=body.job_title,
            company=body.company,
            location=body.location,
            experience_years=body.experience_years,
            current_salary=body.current_salary,
            skills_summary=body.skills_summary,
            application_id=body.application_id,
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Salary analysis failed. Please try again.")


@router.get("/{analysis_id}")
@limiter.limit("30/minute")
async def get_analysis(
    request: Request,
    analysis_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific salary analysis."""
    _validate_uuid(analysis_id, "analysis_id")
    service = SalaryService()
    analysis = await service.get_analysis(analysis_id, current_user["id"])
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    return analysis


@router.get("/")
@limiter.limit("30/minute")
async def get_analyses(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get recent salary analyses."""
    service = SalaryService()
    return await service.get_user_analyses(current_user["id"])
