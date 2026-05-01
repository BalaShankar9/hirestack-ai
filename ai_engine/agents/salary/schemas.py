"""Pydantic v2 schemas for Salary Negotiation Generator (S16-P3)."""
from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CompetingOffer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    company: str = ""
    base: float = 0.0
    total_comp: float = 0.0


class OfferDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str = Field(..., min_length=2, max_length=200)
    level: str = Field("mid", max_length=50)
    location: str = Field("remote", max_length=100)
    base: float = Field(..., ge=0)
    bonus: float = Field(0.0, ge=0)
    equity: float = Field(0.0, ge=0)
    sign_on: float = Field(0.0, ge=0)
    company: str = Field("", max_length=200)
    competing_offers: List[CompetingOffer] = Field(default_factory=list)
    your_leverage: Optional[str] = Field(
        None, max_length=2000,
        description="Free-text: years_exp, hot domains, alt offers, etc.",
    )


class MarketBand(BaseModel):
    model_config = ConfigDict(extra="ignore")
    role: str
    level: str
    location: str
    p25: float = Field(0.0, ge=0)
    p50: float = Field(0.0, ge=0)
    p75: float = Field(0.0, ge=0)
    p90: float = Field(0.0, ge=0)
    source: str = "seed_v1"


class NegotiationPlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    counter_base: float
    counter_total_comp: float
    target_range_low: float
    target_range_high: float
    walk_away: float
    rationale: List[str] = Field(default_factory=list)
    red_flags: List[str] = Field(default_factory=list)
    market_band: MarketBand


class NegotiationScript(BaseModel):
    model_config = ConfigDict(extra="ignore")
    tone: str = "collaborative"
    opening: str = ""
    anchor: str = ""
    silence_cue: str = ""
    counter: str = ""
    close: str = ""
    talking_points: List[str] = Field(default_factory=list)
    email_template: str = ""


class NegotiationReport(BaseModel):
    model_config = ConfigDict(extra="ignore")
    offer: OfferDetails
    plan: NegotiationPlan
    script: NegotiationScript
    latency_ms: Optional[int] = None
