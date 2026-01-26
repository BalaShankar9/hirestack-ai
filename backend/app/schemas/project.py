"""Project schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


class ProjectMilestone(BaseSchema):
    """Project milestone."""
    id: str
    title: str
    description: str
    tasks: List[str]
    deliverables: List[str]
    week: int
    status: str = "pending"


class ProjectImplementation(BaseSchema):
    """Project implementation guide."""
    overview: str
    architecture: Optional[str] = None
    setup_steps: List[str]
    milestones: List[ProjectMilestone]
    testing_strategy: Optional[str] = None
    deployment_guide: Optional[str] = None
    best_practices: Optional[List[str]] = None


class ProjectResource(BaseSchema):
    """Resource for project implementation."""
    title: str
    type: str  # documentation, tutorial, library, tool
    url: str
    description: Optional[str] = None


class ProjectCreate(BaseSchema):
    """Schema for creating a project."""
    title: str
    description: Optional[str] = None
    roadmap_id: Optional[UUID] = None
    tech_stack: Optional[List[str]] = None
    difficulty: Optional[str] = None
    estimated_duration: Optional[str] = None


class ProjectUpdate(BaseSchema):
    """Schema for updating a project."""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None


class ProjectResponse(IDMixin, TimestampMixin):
    """Full project response."""
    user_id: UUID
    roadmap_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    summary: Optional[str] = None
    tech_stack: Optional[List[str]] = None
    difficulty: Optional[str] = None
    estimated_duration: Optional[str] = None
    implementation_guide: Optional[ProjectImplementation] = None
    milestones: Optional[List[ProjectMilestone]] = None
    features: Optional[List[str]] = None
    skills_developed: Optional[List[str]] = None
    learning_outcomes: Optional[List[str]] = None
    resources: Optional[List[ProjectResource]] = None
    references: Optional[List[str]] = None
    status: str = "suggested"
    progress: int = 0
    repo_url: Optional[str] = None
    demo_url: Optional[str] = None

    class Config:
        from_attributes = True
