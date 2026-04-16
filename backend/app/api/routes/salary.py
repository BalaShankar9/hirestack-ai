"""
Salary Coach routes - Salary analysis and negotiation coaching (Supabase)
"""
import uuid as _uuid
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import structlog

from app.services.salary import SalaryService
from app.api.deps import get_current_user
from app.core.security import limiter

router = APIRouter()
logger = structlog.get_logger()


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


@limiter.limit("5/minute")
@router.post("/analyze")
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
    except Exception as e:
        logger.error("salary_analysis_failed", error=str(e), user_id=current_user["id"])
        raise HTTPException(status_code=500, detail="Salary analysis failed. Please try again.")


@limiter.limit("30/minute")
@router.get("/{analysis_id}")
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


@limiter.limit("30/minute")
@router.get("/")
async def get_analyses(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get recent salary analyses."""
    service = SalaryService()
    return await service.get_user_analyses(current_user["id"])
