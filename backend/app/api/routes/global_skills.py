"""
Global Skills & Development API routes — profile-wide skills, gaps, and learning goals.
"""
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.services.global_skills import GlobalSkillsService
from app.api.deps import get_current_user
from app.core.security import limiter
import structlog

logger = structlog.get_logger()

router = APIRouter()


# ── Request models ───────────────────────────────────────────────────

class UpsertSkillRequest(BaseModel):
    skill_name: str = Field(..., min_length=1, max_length=200)
    category: Optional[str] = Field(None, pattern="^(technical|soft_skill|tool|language|framework|methodology|certification|domain|other)$")
    proficiency: Optional[str] = Field(None, pattern="^(beginner|intermediate|advanced|expert)$")
    years_experience: Optional[float] = Field(None, ge=0, le=50)
    source: str = Field("manual", pattern="^(manual|resume_parse|gap_analysis|learning|evidence)$")


class UpdateGapStatusRequest(BaseModel):
    status: str = Field(..., pattern="^(open|in_progress|closed|dismissed)$")


class CreateGoalRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    target_skills: List[str] = Field(default_factory=list)
    goal_type: str = Field("general", pattern="^(skill_acquisition|certification|career_transition|promotion_readiness|industry_knowledge|general)$")
    target_date: Optional[str] = None


class UpdateGoalRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = Field(None, max_length=2000)
    target_skills: Optional[List[str]] = None
    goal_type: Optional[str] = None
    status: Optional[str] = Field(None, pattern="^(active|completed|paused|archived)$")
    target_date: Optional[str] = None
    progress_pct: Optional[int] = Field(None, ge=0, le=100)


# ── Skills ───────────────────────────────────────────────────────────

@router.get("/skills")
@limiter.limit("30/minute")
async def list_skills(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List all user skills (global profile)."""
    svc = GlobalSkillsService()
    return await svc.list_skills(current_user["id"])


@router.post("/skills")
@limiter.limit("30/minute")
async def upsert_skill(
    request: Request,
    body: UpsertSkillRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Add or update a skill in the global profile."""
    svc = GlobalSkillsService()
    return await svc.upsert_skill(current_user["id"], body.model_dump())


@router.delete("/skills/{skill_id}")
@limiter.limit("30/minute")
async def delete_skill(
    request: Request,
    skill_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Remove a skill from the global profile."""
    svc = GlobalSkillsService()
    await svc.delete_skill(current_user["id"], skill_id)
    return {"ok": True}


# ── Skill Gaps ───────────────────────────────────────────────────────

@router.get("/gaps")
@limiter.limit("30/minute")
async def list_gaps(
    request: Request,
    status: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List global skill gaps (aggregated across applications)."""
    svc = GlobalSkillsService()
    return await svc.list_gaps(current_user["id"], status=status)


@router.post("/gaps/sync")
@limiter.limit("5/minute")
async def sync_gaps(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Sync skill gaps from all applications into the global profile."""
    svc = GlobalSkillsService()
    return await svc.sync_gaps_from_applications(current_user["id"])


@router.patch("/gaps/{gap_id}")
@limiter.limit("30/minute")
async def update_gap_status(
    request: Request,
    gap_id: str,
    body: UpdateGapStatusRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a global skill gap's status."""
    svc = GlobalSkillsService()
    result = await svc.update_gap_status(current_user["id"], gap_id, body.status)
    if not result:
        raise HTTPException(status_code=404, detail="Gap not found")
    return result


# ── Learning Goals ───────────────────────────────────────────────────

@router.get("/goals")
@limiter.limit("30/minute")
async def list_goals(
    request: Request,
    status: Optional[str] = Query(None),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """List learning goals."""
    svc = GlobalSkillsService()
    return await svc.list_goals(current_user["id"], status=status)


@router.post("/goals")
@limiter.limit("10/minute")
async def create_goal(
    request: Request,
    body: CreateGoalRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Create a new learning goal."""
    svc = GlobalSkillsService()
    return await svc.create_goal(current_user["id"], body.model_dump())


@router.patch("/goals/{goal_id}")
@limiter.limit("30/minute")
async def update_goal(
    request: Request,
    goal_id: str,
    body: UpdateGoalRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Update a learning goal."""
    svc = GlobalSkillsService()
    result = await svc.update_goal(current_user["id"], goal_id, body.model_dump(exclude_none=True))
    if not result:
        raise HTTPException(status_code=404, detail="Goal not found")
    return result


@router.delete("/goals/{goal_id}")
@limiter.limit("10/minute")
async def delete_goal(
    request: Request,
    goal_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Delete a learning goal."""
    svc = GlobalSkillsService()
    await svc.delete_goal(current_user["id"], goal_id)
    return {"ok": True}


# ── Profile Summary ──────────────────────────────────────────────────

@router.get("/summary")
@limiter.limit("30/minute")
async def get_summary(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """Get a combined skills/gaps/goals summary for the sidebar."""
    svc = GlobalSkillsService()
    return await svc.get_profile_summary(current_user["id"])
