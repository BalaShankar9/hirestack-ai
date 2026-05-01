"""S17-P2 — Culture-fit Pydantic v2 schemas."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

ValueDimension = Literal[
    "ownership",
    "collaboration",
    "customer_obsession",
    "innovation",
    "execution_speed",
    "craft_quality",
    "transparency",
    "diversity_inclusion",
    "long_term_thinking",
    "frugality",
    "learning_growth",
    "wellbeing",
]


class CultureSignal(BaseModel):
    """A single culture cue extracted from public materials."""

    model_config = ConfigDict(extra="ignore")

    dimension: ValueDimension
    evidence: str
    weight: float = Field(default=1.0, ge=0.0, le=3.0)
    source: str = "company_text"


class CultureValueMap(BaseModel):
    """Per-dimension importance scores derived from evidence."""

    model_config = ConfigDict(extra="ignore")

    company: str = ""
    scores: dict[str, float] = Field(default_factory=dict)
    top_dimensions: List[str] = Field(default_factory=list)
    signals: List[CultureSignal] = Field(default_factory=list)


class ValuesQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dimension: ValueDimension
    question: str
    why_asked: str
    listen_for: List[str] = Field(default_factory=list)


class PreparedAnswer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str
    dimension: ValueDimension
    star_situation: str
    star_task: str
    star_action: str
    star_result: str
    talking_points: List[str] = Field(default_factory=list)
    pitfalls: List[str] = Field(default_factory=list)


class CultureFitReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company: str = ""
    value_map: CultureValueMap
    questions: List[ValuesQuestion] = Field(default_factory=list)
    prepared_answers: List[PreparedAnswer] = Field(default_factory=list)
    misalignment_risks: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None
