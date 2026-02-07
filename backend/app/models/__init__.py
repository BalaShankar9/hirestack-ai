"""
HireStack AI - Database Models
With Firestore, we use dictionaries instead of SQLAlchemy models.
This file provides type hints and schemas for Firestore documents.
"""
from typing import TypedDict, Optional, List
from datetime import datetime


class UserDict(TypedDict, total=False):
    """User document schema."""
    id: str
    email: str
    full_name: Optional[str]
    avatar_url: Optional[str]
    is_active: bool
    is_premium: bool
    created_at: datetime
    updated_at: datetime


class ProfileDict(TypedDict, total=False):
    """Profile document schema."""
    id: str
    user_id: str
    raw_resume_text: str
    parsed_data: dict
    skills: List[dict]
    experience: List[dict]
    education: List[dict]
    certifications: List[dict]
    is_primary: bool
    created_at: datetime
    updated_at: datetime


class JobDescriptionDict(TypedDict, total=False):
    """Job description document schema."""
    id: str
    user_id: str
    title: str
    company: Optional[str]
    description: str
    requirements: dict
    parsed_data: dict
    created_at: datetime


class BenchmarkDict(TypedDict, total=False):
    """Benchmark document schema."""
    id: str
    job_description_id: str
    ideal_profile: dict
    ideal_cv: str
    ideal_cover_letter: str
    ideal_portfolio: dict
    ideal_case_studies: dict
    ideal_action_plan: dict
    compatibility_criteria: dict
    created_at: datetime


class GapReportDict(TypedDict, total=False):
    """Gap report document schema."""
    id: str
    user_id: str
    profile_id: str
    benchmark_id: str
    compatibility_score: int
    skill_gaps: List[dict]
    experience_gaps: List[dict]
    certification_gaps: List[dict]
    project_gaps: List[dict]
    recommendations: List[dict]
    created_at: datetime


class RoadmapDict(TypedDict, total=False):
    """Roadmap document schema."""
    id: str
    user_id: str
    gap_report_id: str
    title: str
    learning_path: List[dict]
    milestones: List[dict]
    timeline: dict
    resources: List[dict]
    created_at: datetime


class ProjectDict(TypedDict, total=False):
    """Project document schema."""
    id: str
    user_id: str
    roadmap_id: str
    title: str
    description: str
    tech_stack: List[str]
    implementation_guide: dict
    status: str
    created_at: datetime


class DocumentDict(TypedDict, total=False):
    """Document (CV, cover letter, etc.) schema."""
    id: str
    user_id: str
    document_type: str
    content: str
    doc_metadata: dict
    version: int
    created_at: datetime


class ExportDict(TypedDict, total=False):
    """Export document schema."""
    id: str
    user_id: str
    document_ids: List[str]
    format: str
    file_url: str
    created_at: datetime


class AnalyticsDict(TypedDict, total=False):
    """Analytics event schema."""
    id: str
    user_id: str
    event_type: str
    event_data: dict
    created_at: datetime


__all__ = [
    "UserDict",
    "ProfileDict",
    "JobDescriptionDict",
    "BenchmarkDict",
    "GapReportDict",
    "RoadmapDict",
    "ProjectDict",
    "DocumentDict",
    "ExportDict",
    "AnalyticsDict",
]
