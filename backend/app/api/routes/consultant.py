"""
Career Consultant routes - Roadmaps and recommendations (Firestore)
"""
from typing import Dict, Any, Optional, Literal

from app.core.security import limiter
from fastapi import APIRouter, Depends, HTTPException, status, Request

from app.services.roadmap import RoadmapService
from app.api.deps import get_current_user, validate_uuid
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

router = APIRouter()


class GenerateRoadmapRequest(BaseModel):
    gap_report_id: Optional[str] = Field(None, max_length=100)
    title: Optional[str] = Field(None, max_length=300)


class UpdateProgressRequest(BaseModel):
    milestone_id: str = Field(..., min_length=1, max_length=100)
    status: Literal["pending", "in_progress", "completed"] = "pending"


@limiter.limit("5/minute")
@router.post("/roadmap")
async def generate_roadmap(
    request: Request,
    body: GenerateRoadmapRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Generate a career improvement roadmap."""
    service = RoadmapService()
    try:
        return await service.generate_roadmap(
            user_id=current_user["id"],
            gap_report_id=body.gap_report_id,
            title=body.title,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except Exception as e:
        logger.error("unexpected_error", error=str(e), endpoint="generate_roadmap")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="An unexpected error occurred")


@limiter.limit("5/minute")
@router.get("/roadmaps")
async def list_roadmaps(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user's roadmaps."""
    service = RoadmapService()
    return await service.get_user_roadmaps(current_user["id"])


@limiter.limit("5/minute")
@router.get("/roadmap/{roadmap_id}")
async def get_roadmap(
    request: Request,
    roadmap_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a specific roadmap."""
    validate_uuid(roadmap_id, "roadmap_id")
    service = RoadmapService()
    roadmap = await service.get_roadmap(roadmap_id, current_user["id"])
    if not roadmap:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")
    return roadmap


@limiter.limit("5/minute")
@router.put("/roadmap/{roadmap_id}/progress")
async def update_progress(
    request: Request,
    roadmap_id: str,
    body: UpdateProgressRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update milestone progress in a roadmap."""
    validate_uuid(roadmap_id, "roadmap_id")
    service = RoadmapService()
    updated = await service.update_milestone_progress(
        roadmap_id, current_user["id"], body.milestone_id, body.status
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap or milestone not found")
    return {"message": "Progress updated"}


@limiter.limit("5/minute")
@router.delete("/roadmap/{roadmap_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_roadmap(
    request: Request,
    roadmap_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a roadmap."""
    validate_uuid(roadmap_id, "roadmap_id")
    service = RoadmapService()
    deleted = await service.delete_roadmap(roadmap_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Roadmap not found")




class CoachQuestionRequest(BaseModel):
    question: str
    app_id: str


@limiter.limit("5/minute")
@router.post("/coach")
async def ask_coach(
    request: Request,
    req: CoachQuestionRequest,
    current_user: Dict[str, Any] = Depends(get_current_user
),
):
    """Ask the AI coach a question about an application."""
    from app.core.database import get_db, TABLES
    from ai_engine.client import AIClient
    from ai_engine.chains.application_coach import ApplicationCoachChain

    db = get_db()
    app = await db.get(TABLES["applications"], req.app_id)
    if not app or app.get("user_id") != current_user["id"]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")

    facts = app.get("confirmedFacts") or {}
    gaps = app.get("gaps") or {}
    modules = app.get("modules") or {}

    # Build gaps summary
    missing = gaps.get("missingKeywords") or gaps.get("skill_gaps") or []
    gaps_text = ", ".join(
        (g.get("keyword") or g.get("skill") or str(g))[:30] for g in missing[:10]
    ) if isinstance(missing, list) else "No gaps data"

    context = {
        "job_title": facts.get("jobTitle") or app.get("title") or "",
        "company": facts.get("company") or "",
        "match_score": (app.get("scores") or {}).get("match", 0),
        "jd_text": facts.get("jdText") or "",
        "resume_text": facts.get("resumeText") or "",
        "gaps_summary": gaps_text,
        "cv_html": (modules.get("cv") or {}).get("html") or "",
    }

    chain = ApplicationCoachChain(AIClient())
    try:
        return await chain.ask(req.question, context)
    except Exception as e:
        logger.error("coach_error", error=str(e)[:200])
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Coach is unavailable")
