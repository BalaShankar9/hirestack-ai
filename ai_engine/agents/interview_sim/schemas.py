"""
Interview Simulator schemas (Pydantic v2).

Models capture an audio-first practice loop: questions are calibrated to
the role + JD + resume, candidates submit answers, and each turn is
scored against STAR structure + role-signal coverage.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class QuestionKind(str, Enum):
    behavioral = "behavioral"
    technical = "technical"
    situational = "situational"
    motivational = "motivational"
    curveball = "curveball"


class InterviewQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    text: str
    kind: QuestionKind = QuestionKind.behavioral
    signal_target: Optional[str] = Field(
        None, description="The hire-signal this question probes (e.g. ownership, scope, depth)."
    )
    rubric: List[str] = Field(default_factory=list)
    audio_b64: Optional[str] = None  # Optional TTS rendering


class AnswerScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    star_score: float = Field(0.0, ge=0.0, le=1.0)
    signal_coverage: float = Field(0.0, ge=0.0, le=1.0)
    clarity: float = Field(0.0, ge=0.0, le=1.0)
    specificity: float = Field(0.0, ge=0.0, le=1.0)
    overall: float = Field(0.0, ge=0.0, le=1.0)


class InterviewTurn(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: InterviewQuestion
    candidate_answer: Optional[str] = None
    score: Optional[AnswerScore] = None
    feedback: List[str] = Field(default_factory=list)
    suggested_rewrite: Optional[str] = None


class InterviewSession(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    role: str
    audience_hint: Optional[str] = None
    questions: List[InterviewQuestion] = Field(default_factory=list)
    turns: List[InterviewTurn] = Field(default_factory=list)
    cursor: int = 0  # next question index to ask
    finalized: bool = False
    planning_latency_ms: int = 0
    phase_latencies: Dict[str, int] = Field(default_factory=dict)
    phase_statuses: Dict[str, str] = Field(default_factory=dict)


class SessionReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    session_id: str
    role: str
    overall_score: float = Field(0.0, ge=0.0, le=1.0)
    strengths: List[str] = Field(default_factory=list)
    gaps: List[str] = Field(default_factory=list)
    turns: List[InterviewTurn] = Field(default_factory=list)
    latency_ms: int = 0
