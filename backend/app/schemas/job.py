"""Job description schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


class CompanyInfo(BaseSchema):
    """Company information."""
    name: str
    industry: Optional[str] = None
    size: Optional[str] = None
    description: Optional[str] = None
    culture: Optional[str] = None
    values: Optional[List[str]] = None
    website: Optional[str] = None


class ParsedJobDescription(BaseSchema):
    """Parsed job description data."""
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None  # full-time, part-time, contract
    experience_level: Optional[str] = None  # entry, mid, senior, lead
    salary_range: Optional[str] = None
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    company_info: Optional[CompanyInfo] = None


class JobDescriptionCreate(BaseSchema):
    """Schema for creating a job description."""
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    experience_level: Optional[str] = None
    salary_range: Optional[str] = None
    description: str
    source_url: Optional[str] = None


class JobDescriptionUpdate(BaseSchema):
    """Schema for updating a job description."""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    experience_level: Optional[str] = None
    salary_range: Optional[str] = None
    description: Optional[str] = None


class JobDescriptionResponse(IDMixin, TimestampMixin):
    """Schema for job description response."""
    user_id: UUID
    title: str
    company: Optional[str] = None
    location: Optional[str] = None
    job_type: Optional[str] = None
    experience_level: Optional[str] = None
    salary_range: Optional[str] = None
    description: str
    required_skills: Optional[List[str]] = None
    preferred_skills: Optional[List[str]] = None
    requirements: Optional[List[str]] = None
    responsibilities: Optional[List[str]] = None
    benefits: Optional[List[str]] = None
    company_info: Optional[CompanyInfo] = None
    source_url: Optional[str] = None

    class Config:
        from_attributes = True
