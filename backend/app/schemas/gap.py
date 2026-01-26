"""Gap analysis schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


class SkillGap(BaseSchema):
    """Individual skill gap."""
    skill: str
    required_level: str
    current_level: Optional[str] = None
    gap_severity: str = Field(..., pattern="^(none|minor|moderate|major|critical)$")
    recommendation: str
    resources: Optional[List[str]] = None


class ExperienceGap(BaseSchema):
    """Experience gap."""
    area: str
    required_years: Optional[int] = None
    current_years: Optional[int] = None
    gap_description: str
    recommendation: str
    how_to_gain: Optional[List[str]] = None


class EducationGap(BaseSchema):
    """Education gap."""
    requirement: str
    current_status: str
    gap_severity: str
    alternatives: Optional[List[str]] = None
    recommendation: str


class CertificationGap(BaseSchema):
    """Certification gap."""
    certification: str
    importance: str  # required, preferred, nice-to-have
    recommendation: str
    study_resources: Optional[List[str]] = None


class ProjectGap(BaseSchema):
    """Project/portfolio gap."""
    project_type: str
    importance: str
    current_status: str
    recommendation: str
    project_ideas: Optional[List[str]] = None


class Strength(BaseSchema):
    """User strength that matches/exceeds benchmark."""
    area: str
    description: str
    advantage: str
    how_to_leverage: str


class Recommendation(BaseSchema):
    """Improvement recommendation."""
    priority: int = Field(..., ge=1, le=5)
    category: str
    title: str
    description: str
    action_items: List[str]
    estimated_effort: Optional[str] = None
    impact: str  # low, medium, high, critical


class GapSummary(BaseSchema):
    """Brief gap analysis summary."""
    compatibility_score: int = Field(..., ge=0, le=100)
    skill_score: int = Field(..., ge=0, le=100)
    experience_score: int = Field(..., ge=0, le=100)
    education_score: int = Field(..., ge=0, le=100)
    certification_score: int = Field(..., ge=0, le=100)
    project_score: int = Field(..., ge=0, le=100)
    top_gaps: List[str]
    top_strengths: List[str]
    readiness_level: str  # not-ready, needs-work, competitive, strong-match


class GapAnalysisRequest(BaseSchema):
    """Request for gap analysis."""
    profile_id: UUID
    benchmark_id: UUID


class GapReportResponse(IDMixin):
    """Full gap report response."""
    user_id: UUID
    profile_id: UUID
    benchmark_id: UUID
    compatibility_score: int = Field(..., ge=0, le=100)
    skill_score: int = Field(..., ge=0, le=100)
    experience_score: int = Field(..., ge=0, le=100)
    education_score: int = Field(..., ge=0, le=100)
    certification_score: int = Field(..., ge=0, le=100)
    project_score: int = Field(..., ge=0, le=100)
    skill_gaps: List[SkillGap]
    experience_gaps: List[ExperienceGap]
    education_gaps: Optional[List[EducationGap]] = None
    certification_gaps: Optional[List[CertificationGap]] = None
    project_gaps: Optional[List[ProjectGap]] = None
    strengths: List[Strength]
    recommendations: List[Recommendation]
    priority_actions: List[str]
    summary: GapSummary
    created_at: datetime

    class Config:
        from_attributes = True
