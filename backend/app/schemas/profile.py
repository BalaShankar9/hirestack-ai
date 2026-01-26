"""Profile schemas"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

from pydantic import Field

from app.schemas.base import BaseSchema, TimestampMixin, IDMixin


class ContactInfo(BaseSchema):
    """Contact information."""
    email: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    website: Optional[str] = None


class Skill(BaseSchema):
    """Skill entry."""
    name: str
    level: Optional[str] = None  # beginner, intermediate, advanced, expert
    years: Optional[float] = None
    category: Optional[str] = None  # technical, soft, language


class Experience(BaseSchema):
    """Work experience entry."""
    company: str
    title: str
    location: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    is_current: bool = False
    description: Optional[str] = None
    achievements: Optional[List[str]] = None
    technologies: Optional[List[str]] = None


class Education(BaseSchema):
    """Education entry."""
    institution: str
    degree: str
    field: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None
    achievements: Optional[List[str]] = None


class Certification(BaseSchema):
    """Certification entry."""
    name: str
    issuer: Optional[str] = None
    date: Optional[str] = None
    expiry: Optional[str] = None
    credential_id: Optional[str] = None
    url: Optional[str] = None


class ProfileProject(BaseSchema):
    """Project in profile."""
    name: str
    description: Optional[str] = None
    role: Optional[str] = None
    technologies: Optional[List[str]] = None
    url: Optional[str] = None
    achievements: Optional[List[str]] = None


class ParsedProfile(BaseSchema):
    """Fully parsed profile data."""
    name: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    contact_info: Optional[ContactInfo] = None
    skills: Optional[List[Skill]] = None
    experience: Optional[List[Experience]] = None
    education: Optional[List[Education]] = None
    certifications: Optional[List[Certification]] = None
    projects: Optional[List[ProfileProject]] = None
    languages: Optional[List[Dict[str, str]]] = None
    achievements: Optional[List[str]] = None


class ResumeUpload(BaseSchema):
    """Resume upload request."""
    file_type: str = Field(..., pattern="^(pdf|docx|doc|txt)$")


class ProfileCreate(BaseSchema):
    """Schema for creating a profile."""
    name: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    raw_resume_text: Optional[str] = None
    file_url: Optional[str] = None
    file_type: Optional[str] = None
    parsed_data: Optional[Dict[str, Any]] = None
    is_primary: bool = False


class ProfileUpdate(BaseSchema):
    """Schema for updating a profile."""
    name: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    skills: Optional[List[Skill]] = None
    experience: Optional[List[Experience]] = None
    education: Optional[List[Education]] = None
    certifications: Optional[List[Certification]] = None
    projects: Optional[List[ProfileProject]] = None
    is_primary: Optional[bool] = None


class ProfileResponse(IDMixin, TimestampMixin):
    """Schema for profile response."""
    user_id: UUID
    name: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    file_url: Optional[str] = None
    file_type: Optional[str] = None
    contact_info: Optional[ContactInfo] = None
    skills: Optional[List[Skill]] = None
    experience: Optional[List[Experience]] = None
    education: Optional[List[Education]] = None
    certifications: Optional[List[Certification]] = None
    projects: Optional[List[ProfileProject]] = None
    languages: Optional[List[Dict[str, str]]] = None
    achievements: Optional[List[str]] = None
    is_primary: bool = False

    class Config:
        from_attributes = True
