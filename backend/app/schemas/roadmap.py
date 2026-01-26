"""Roadmap schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


class LearningResource(BaseSchema):
    """Learning resource."""
    title: str
    type: str  # course, book, tutorial, video, documentation
    url: Optional[str] = None
    provider: Optional[str] = None
    duration: Optional[str] = None
    cost: Optional[str] = None
    skill_covered: str
    priority: str = "recommended"  # required, recommended, optional


class RoadmapMilestone(BaseSchema):
    """Roadmap milestone."""
    id: str
    title: str
    description: str
    week: int
    tasks: List[str]
    deliverables: List[str]
    skills_developed: List[str]
    success_criteria: List[str]
    status: str = "pending"  # pending, in_progress, completed


class WeeklyPlan(BaseSchema):
    """Weekly action plan."""
    week: int
    focus: str
    goals: List[str]
    tasks: List[Dict[str, Any]]
    time_commitment: str
    resources: List[LearningResource]


class SkillDevelopment(BaseSchema):
    """Skill development plan."""
    skill: str
    current_level: Optional[str] = None
    target_level: str
    timeline: str
    resources: List[LearningResource]
    practice_projects: Optional[List[str]] = None
    milestones: List[str]


class CertificationPath(BaseSchema):
    """Certification pursuit plan."""
    certification: str
    provider: str
    timeline: str
    prerequisites: Optional[List[str]] = None
    study_plan: List[str]
    resources: List[LearningResource]
    exam_tips: Optional[List[str]] = None


class ExperienceRecommendation(BaseSchema):
    """Experience gaining recommendation."""
    experience_type: str
    description: str
    how_to_gain: List[str]
    timeline: str
    projects: Optional[List[str]] = None
    networking_tips: Optional[List[str]] = None


class RoadmapCreate(BaseSchema):
    """Schema for creating a roadmap."""
    gap_report_id: UUID
    title: Optional[str] = "Career Roadmap"


class RoadmapResponse(IDMixin, TimestampMixin):
    """Full roadmap response."""
    user_id: UUID
    gap_report_id: UUID
    title: str
    description: Optional[str] = None
    learning_path: List[LearningResource]
    milestones: List[RoadmapMilestone]
    timeline: Dict[str, Any]  # Weekly/monthly breakdown
    weekly_plans: Optional[List[WeeklyPlan]] = None
    skill_development: List[SkillDevelopment]
    certification_path: Optional[List[CertificationPath]] = None
    experience_recommendations: Optional[List[ExperienceRecommendation]] = None
    action_items: List[Dict[str, Any]]
    progress: Optional[Dict[str, Any]] = None
    status: str = "active"

    class Config:
        from_attributes = True
