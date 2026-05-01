"""Agent integration for Salary Negotiation Generator (S16-P3)."""
from __future__ import annotations

import re
import time
from typing import Optional

from ai_engine.agents.salary.negotiator import SalaryNegotiator
from ai_engine.agents.salary.schemas import NegotiationReport, OfferDetails
from ai_engine.agents.salary.script_writer import ScriptWriter
from ai_engine.agents.tools import AgentTool, ToolRegistry

_INTENT_RE = re.compile(
    r"\b(salary|compensation|comp|offer)\b.*\bnegotiat\w*\b"
    r"|\b(salary|compensation|comp|offer)\b.*\b(counter|raise)\b"
    r"|\bnegotiat\w*\b.*\b(salary|offer|comp)\b"
    r"|\bcounter\b.*\b(salary|offer|comp)\b",
    re.IGNORECASE,
)


def detect_salary_intent(text: str) -> Optional[dict]:
    if not text:
        return None
    if _INTENT_RE.search(text):
        return {"intent": "salary_negotiate"}
    return None


async def generate_negotiation(
    offer: OfferDetails, *, tone: str = "collaborative"
) -> NegotiationReport:
    t0 = time.monotonic()
    negotiator = SalaryNegotiator()
    plan = negotiator.plan(offer)
    writer = ScriptWriter()
    script = await writer.write(offer, plan, tone=tone)
    return NegotiationReport(
        offer=offer,
        plan=plan,
        script=script,
        latency_ms=int((time.monotonic() - t0) * 1000),
    )


async def _negotiate_tool(args: dict) -> dict:
    offer_data = args.get("offer") or {}
    tone = (args.get("tone") or "collaborative").lower()
    try:
        offer = OfferDetails.model_validate(offer_data)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"invalid offer: {exc}"}
    report = await generate_negotiation(offer, tone=tone)
    return report.model_dump()


def build_salary_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(AgentTool(
        name="generate_salary_negotiation",
        description=("Build a defensible counter-offer plan plus a phone-call "
                     "script and email template for a job offer."),
        parameters={
            "type": "object",
            "properties": {
                "offer": {"type": "object"},
                "tone": {"type": "string"},
            },
            "required": ["offer"],
        },
        fn=_negotiate_tool,
    ))
    return reg
