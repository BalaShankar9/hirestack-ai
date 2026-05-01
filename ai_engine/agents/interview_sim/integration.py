"""
Integration layer for the Interview Simulator.

Exposes:
- detect_interview_intent(text) → Optional[dict]
- build_interview_sim_tools() → ToolRegistry
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

from ai_engine.agents.tools import AgentTool, ToolRegistry

logger = logging.getLogger(__name__)


_KEYWORDS = (
    "interview", "mock interview", "practice interview", "interview prep",
    "behavioral question", "interview question",
)
_VERBS = ("practice", "prep", "rehearse", "simulate", "give me", "run a")


def detect_interview_intent(text: str) -> Optional[Dict[str, Any]]:
    if not text or not isinstance(text, str):
        return None
    lo = text.lower()
    if not any(k in lo for k in _KEYWORDS):
        return None
    if not (any(v in lo for v in _VERBS) or "mock interview" in lo or "practice interview" in lo):
        return None

    role = _extract_role(text)
    if not role:
        return None
    return {"role": role}


_ROLE_RE = re.compile(
    r"\b(?:for|as a?|of a?n?|of)\s+(?:an?\s+)?([A-Za-z][A-Za-z0-9 /+&.-]{2,60})$",
    re.IGNORECASE,
)


def _extract_role(text: str) -> Optional[str]:
    m = _ROLE_RE.search(text.strip().rstrip(".!?"))
    if m:
        return m.group(1).strip()
    return None


# ─── tool registry ───────────────────────────────────────────────────

async def _start_interview_sim_tool(**kwargs: Any) -> dict:
    from ai_engine.agents.interview_sim.orchestrator import InterviewSimulator
    sim = InterviewSimulator()
    session = await sim.start_session(
        role=kwargs.get("role", ""),
        jd=kwargs.get("jd"),
        resume=kwargs.get("resume"),
        question_count=int(kwargs.get("question_count") or 10),
        with_audio=bool(kwargs.get("with_audio", False)),
    )
    first = sim.next_question(session)
    return {
        "session_id": session.session_id,
        "role": session.role,
        "question_count": len(session.questions),
        "first_question": first.model_dump() if first else None,
        "questions": [q.model_dump() for q in session.questions],
    }


def build_interview_sim_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(AgentTool(
        name="start_interview_sim",
        description=(
            "Start an interview practice session for a target role. Returns "
            "the session_id, the planned questions, and the first question."
        ),
        parameters={
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "Target job title"},
                "jd": {"type": "string", "description": "Optional job description"},
                "resume": {"type": "string", "description": "Optional candidate resume"},
                "question_count": {"type": "integer", "default": 10},
                "with_audio": {"type": "boolean", "default": False},
            },
            "required": ["role"],
        },
        fn=_start_interview_sim_tool,
    ))
    return reg
