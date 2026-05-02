"""S18 — Recon Swarm v2 schemas (Pydantic v2)."""
from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

# ─── Field-level confidence wrapper ───────────────────────────────

ConfidenceLevel = Literal["high", "medium", "low", "unknown"]


class IntelField(BaseModel):
    """A single intel field with provenance + confidence."""
    model_config = ConfigDict(extra="ignore")
    value: Any
    confidence: ConfidenceLevel = "unknown"
    sources: List[str] = Field(default_factory=list)


# ─── Raw provider output ──────────────────────────────────────────

class ProviderResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    provider: str
    layer: int
    success: bool
    latency_ms: int = 0
    raw: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


# ─── Structured 50-field company intel ────────────────────────────

class CompanyIntelV2(BaseModel):
    """Fused, structured intel — 50+ fields grouped by category."""
    model_config = ConfigDict(extra="ignore")
    company: str

    # Company overview
    legal_name: IntelField = Field(default_factory=lambda: IntelField(value=None))
    website: IntelField = Field(default_factory=lambda: IntelField(value=None))
    description: IntelField = Field(default_factory=lambda: IntelField(value=None))
    industry: IntelField = Field(default_factory=lambda: IntelField(value=None))
    sub_industries: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    headquarters: IntelField = Field(default_factory=lambda: IntelField(value=None))
    founded_year: IntelField = Field(default_factory=lambda: IntelField(value=None))
    company_stage: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # Funding & financial
    total_funding_usd: IntelField = Field(default_factory=lambda: IntelField(value=None))
    last_round: IntelField = Field(default_factory=lambda: IntelField(value=None))
    last_round_date: IntelField = Field(default_factory=lambda: IntelField(value=None))
    investors: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    valuation_usd: IntelField = Field(default_factory=lambda: IntelField(value=None))
    is_public: IntelField = Field(default_factory=lambda: IntelField(value=False))
    ticker: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # People
    headcount: IntelField = Field(default_factory=lambda: IntelField(value=None))
    eng_headcount: IntelField = Field(default_factory=lambda: IntelField(value=None))
    leadership: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    hiring_managers: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    open_roles_count: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # Tech & product
    tech_stack: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    products: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    github_orgs: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    repo_count: IntelField = Field(default_factory=lambda: IntelField(value=None))
    languages: IntelField = Field(default_factory=lambda: IntelField(value=[]))

    # Market & momentum
    competitors: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    recent_news: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    product_launches: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    patents_count: IntelField = Field(default_factory=lambda: IntelField(value=None))
    research_papers: IntelField = Field(default_factory=lambda: IntelField(value=[]))

    # Reputation
    glassdoor_rating: IntelField = Field(default_factory=lambda: IntelField(value=None))
    glassdoor_themes: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    twitter_handle: IntelField = Field(default_factory=lambda: IntelField(value=None))
    twitter_sentiment: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # Culture
    values: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    benefits: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    work_style: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # External knowledge-base deep links
    wikipedia_url: IntelField = Field(default_factory=lambda: IntelField(value=None))
    wikidata_url: IntelField = Field(default_factory=lambda: IntelField(value=None))
    wikidata_qid: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # SEC (public companies)
    sec_risk_factors: IntelField = Field(default_factory=lambda: IntelField(value=[]))
    sec_revenue_usd: IntelField = Field(default_factory=lambda: IntelField(value=None))

    # Meta
    profile_completeness: float = 0.0
    field_count: int = 0
    high_confidence_count: int = 0


# ─── Application weaponization ────────────────────────────────────

class ApplicationKit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    resume_bullet_hooks: List[str] = Field(default_factory=list)
    cover_letter_hooks: List[str] = Field(default_factory=list)
    interview_questions: List[str] = Field(default_factory=list)
    talking_points: List[str] = Field(default_factory=list)
    tech_stack_matches: List[str] = Field(default_factory=list)
    differentiation_angles: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)


# ─── Top-level request + report ───────────────────────────────────

class ReconSwarmRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    company: str
    role_target: Optional[str] = None
    candidate_skills: List[str] = Field(default_factory=list)
    candidate_values: List[str] = Field(default_factory=list)
    website: Optional[str] = None
    budget_seconds: int = Field(180, ge=10, le=600)
    use_cache: bool = True


class ReconSwarmReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    company: str
    intel: CompanyIntelV2
    application_kit: ApplicationKit
    provider_results: List[ProviderResult]
    layers_completed: List[int]
    cache_hit: bool = False
    total_latency_ms: int = 0
    budget_seconds: int = 180
