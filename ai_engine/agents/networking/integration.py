"""S17-P1 — Networking integration: intent + tools + helpers."""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

from ai_engine.agents.tools import AgentTool, ToolRegistry

from .email_writer import EmailWriter
from .schemas import EmailDraft, OutreachContext, OutreachSequence
from .sequence_planner import SequencePlanner

_INTENT_RE = re.compile(
    r"\b(networking|outreach|cold)\b.*\b(email|message|note)\b"
    r"|\b(email|message|reach out|introduce myself|reconnect)\b.*"
    r"\b(referral|recruiter|hiring manager|mentor|alum|alumna|alumnus)\b"
    r"|\bcoffee chat\b"
    r"|\binformational interview\b",
    re.IGNORECASE,
)


def detect_networking_intent(text: str) -> Optional[str]:
    if not text:
        return None
    m = _INTENT_RE.search(text)
    return m.group(0) if m else None


async def draft_email(
    ctx: Dict[str, Any],
    ask_type: Optional[str] = None,
    tone: str = "warm",
    ai_client: Optional[Any] = None,
) -> EmailDraft:
    return await EmailWriter(ai_client=ai_client).write(
        OutreachContext(**ctx), ask_type=ask_type, tone=tone,
    )


async def plan_sequence(
    ctx: Dict[str, Any],
    follow_up_count: int = 2,
    ai_client: Optional[Any] = None,
) -> OutreachSequence:
    return await SequencePlanner(ai_client=ai_client).plan(
        OutreachContext(**ctx), follow_up_count=follow_up_count,
    )


async def _draft_email_tool(**kwargs: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    draft = await draft_email(
        ctx=kwargs.get("ctx") or {},
        ask_type=kwargs.get("ask_type"),
        tone=kwargs.get("tone", "warm"),
    )
    return {
        "draft": draft.model_dump(),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


async def _plan_sequence_tool(**kwargs: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    seq = await plan_sequence(
        ctx=kwargs.get("ctx") or {},
        follow_up_count=int(kwargs.get("follow_up_count", 2)),
    )
    return {
        "sequence": seq.model_dump(),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def build_networking_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        AgentTool(
            name="draft_outreach_email",
            description="Draft a single personalized networking email.",
            parameters={
                "type": "object",
                "properties": {
                    "ctx": {
                        "type": "object",
                        "description": "OutreachContext fields.",
                    },
                    "ask_type": {"type": "string"},
                    "tone": {"type": "string"},
                },
                "required": ["ctx"],
            },
            fn=_draft_email_tool,
        )
    )
    reg.register(
        AgentTool(
            name="plan_outreach_sequence",
            description="Plan an initial outreach + follow-up cadence.",
            parameters={
                "type": "object",
                "properties": {
                    "ctx": {"type": "object"},
                    "follow_up_count": {"type": "integer"},
                },
                "required": ["ctx"],
            },
            fn=_plan_sequence_tool,
        )
    )
    return reg
