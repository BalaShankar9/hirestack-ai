"""Benchmark schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin
from app.schemas.profile import Skill, Experience, Education, Certification


class IdealCandidate(BaseSchema):
    """Ideal candidate profile for benchmark."""
    name: str = "Ideal Candidate"
    title: str
    summary: str
    years_experience: int
    skills: List[Skill]
    experience: List[Experience]
    education: List[Education]
    certifications: Optional[List[Certification]] = None
    key_strengths: List[str]
    industry_knowledge: List[str]
    soft_skills: List[str]


class IdealDocument(BaseSchema):
    """Ideal document template."""
    type: str
    title: str
    content: str
    sections: Optional[List[Dict[str, Any]]] = None


class CaseStudy(BaseSchema):
    """Ideal case study."""
    title: str
    problem: str
    approach: str
    solution: str
    results: List[str]
    technologies: List[str]
    metrics: Optional[Dict[str, Any]] = None


class ActionPlan(BaseSchema):
    """3-month action plan."""
    title: str
    objectives: List[str]
    month1: Dict[str, Any]
    month2: Dict[str, Any]
    month3: Dict[str, Any]
    deliverables: List[str]
    success_metrics: List[str]


class PortfolioProject(BaseSchema):
    """Portfolio project example."""
    name: str
    description: str
    role: str
    technologies: List[str]
    challenges: List[str]
    outcomes: List[str]
    url: Optional[str] = None


class ScoringCriteria(BaseSchema):
    """Scoring criteria weights."""
    skills: float = 0.25
    experience: float = 0.30
    education: float = 0.15
    certifications: float = 0.10
    projects: float = 0.20


class BenchmarkCreate(BaseSchema):
    """Schema for creating a benchmark."""
    job_description_id: UUID


class BenchmarkSummary(BaseSchema):
    """Brief benchmark summary."""
    id: UUID
    job_title: str
    company: Optional[str]
    ideal_title: str
    years_experience: int
    top_skills: List[str]
    created_at: datetime


class BenchmarkResponse(IDMixin, TimestampMixin):
    """Full benchmark response."""
    job_description_id: UUID
    ideal_profile: IdealCandidate
    ideal_skills: List[Skill]
    ideal_experience: List[Experience]
    ideal_education: List[Education]
    ideal_certifications: Optional[List[str]] = None
    ideal_cv: str
    ideal_cover_letter: str
    ideal_portfolio: Optional[List[PortfolioProject]] = None
    ideal_case_studies: Optional[List[CaseStudy]] = None
    ideal_action_plan: Optional[ActionPlan] = None
    ideal_proposals: Optional[List[Dict[str, Any]]] = None
    compatibility_criteria: Optional[Dict[str, Any]] = None
    scoring_weights: Optional[ScoringCriteria] = None
    version: int = 1
    status: str = "generated"

    class Config:
        from_attributes = True
