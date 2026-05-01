"""Pydantic v2 schemas for LinkedIn Profile Optimizer (S16-P2)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperienceItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field("", max_length=200)
    company: str = Field("", max_length=200)
    duration: str = Field("", max_length=100)
    description: str = Field("", max_length=4000)


class LinkedInProfile(BaseModel):
    model_config = ConfigDict(extra="ignore")
    headline: str = Field("", max_length=300)
    about: str = Field("", max_length=4000)
    experience: List[ExperienceItem] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    education: List[str] = Field(default_factory=list)


class ProfileScore(BaseModel):
    model_config = ConfigDict(extra="ignore")
    overall: float = Field(0.0, ge=0.0, le=1.0)
    headline: float = Field(0.0, ge=0.0, le=1.0)
    about: float = Field(0.0, ge=0.0, le=1.0)
    experience: float = Field(0.0, ge=0.0, le=1.0)
    skills: float = Field(0.0, ge=0.0, le=1.0)
    keyword_density: float = Field(0.0, ge=0.0, le=1.0)
    quantified_achievements: int = 0
    feedback: List[str] = Field(default_factory=list)


class OptimizationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    section: str
    original: str
    optimized: str
    score_before: float = Field(0.0, ge=0.0, le=1.0)
    score_after: float = Field(0.0, ge=0.0, le=1.0)
    rationale: str = ""


class HeadlineVariant(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(..., max_length=300)
    hook_type: str = Field(..., description="value-prop|results|authority|curiosity")
    score: float = Field(0.0, ge=0.0, le=1.0)


class OptimizationReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    target_role: str
    score_before: ProfileScore
    score_after: ProfileScore
    results: List[OptimizationResult] = Field(default_factory=list)
    headline_variants: List[HeadlineVariant] = Field(default_factory=list)
    latency_ms: Optional[int] = None
