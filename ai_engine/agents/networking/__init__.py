"""S17-P1 — Networking Email Generator package surface."""
from __future__ import annotations

from .integration import (
    build_networking_tools,
    detect_networking_intent,
    draft_email,
    plan_sequence,
)
from .schemas import EmailDraft, OutreachContext, OutreachSequence
from .email_writer import EmailWriter
from .sequence_planner import SequencePlanner
from .personalization_scorer import score_personalization

__all__ = [
    "EmailDraft",
    "OutreachContext",
    "OutreachSequence",
    "EmailWriter",
    "SequencePlanner",
    "score_personalization",
    "build_networking_tools",
    "detect_networking_intent",
    "draft_email",
    "plan_sequence",
]
