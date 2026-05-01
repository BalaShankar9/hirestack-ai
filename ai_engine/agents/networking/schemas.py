"""S17-P1 — Networking outreach Pydantic v2 schemas."""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

AskType = Literal[
    "referral", "coffee_chat", "advice", "info_interview", "reconnect"
]


class OutreachContext(BaseModel):
    """Inputs the writer uses to personalize an outreach email."""

    model_config = ConfigDict(extra="ignore")

    sender_name: str
    sender_role: str = ""
    target_name: str
    target_role: str = ""
    target_company: str = ""
    shared_context: str = Field(
        default="",
        description=(
            "Anything genuine the sender can reference: school, mutual "
            "contact, a talk the target gave, a product launch, etc."
        ),
    )
    ask_type: AskType = "coffee_chat"
    your_pitch: str = Field(
        default="",
        description="One-line value prop / current project / why-you.",
    )
    target_url: Optional[str] = None


class EmailDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    subject: str
    body: str
    tone: str = "warm"
    word_count: int = 0
    personalization_score: float = 0.0
    cta: str = ""


class OutreachSequence(BaseModel):
    model_config = ConfigDict(extra="ignore")

    initial: EmailDraft
    follow_ups: List[EmailDraft] = Field(default_factory=list)
    rationale: List[str] = Field(default_factory=list)
    send_cadence_days: List[int] = Field(default_factory=list)
