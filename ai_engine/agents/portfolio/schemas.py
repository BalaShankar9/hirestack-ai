"""S17-P3 — Portfolio site Pydantic v2 schemas."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

Theme = Literal["minimal", "professional", "creative", "developer"]


class ProjectEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str
    description: str
    tech_stack: List[str] = Field(default_factory=list)
    link: Optional[str] = None
    image: Optional[str] = None


class ExperienceEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")
    company: str
    role: str
    start: Optional[str] = None
    end: Optional[str] = None
    bullets: List[str] = Field(default_factory=list)


class PortfolioInput(BaseModel):
    model_config = ConfigDict(extra="ignore")
    candidate_name: str
    headline: str = ""
    summary: str = ""
    contact: Dict[str, str] = Field(default_factory=dict)
    projects: List[ProjectEntry] = Field(default_factory=list)
    experience: List[ExperienceEntry] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    theme: Theme = "professional"


class PortfolioSection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str
    title: str
    html: str


class PortfolioSite(BaseModel):
    model_config = ConfigDict(extra="ignore")
    theme: Theme
    slug: str
    html: str
    css: str
    sections: List[PortfolioSection]
    metadata: Dict[str, str] = Field(default_factory=dict)
