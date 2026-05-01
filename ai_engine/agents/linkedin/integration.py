"""Agent integration for LinkedIn Optimizer (S16-P2)."""
from __future__ import annotations

import re
from typing import Optional

from ai_engine.agents.linkedin.optimizer import LinkedInOptimizer
from ai_engine.agents.linkedin.schemas import LinkedInProfile
from ai_engine.agents.tools import AgentTool, ToolRegistry

_INTENT_RE = re.compile(
    r"\b(linkedin|profile)\b.*\b(optimi[sz]e|rewrite|improve|polish|fix)\b"
    r"|\b(optimi[sz]e|rewrite|polish|fix)\b.*\b(linkedin|profile)\b",
    re.IGNORECASE,
)


def detect_linkedin_intent(text: str) -> Optional[dict]:
    if not text:
        return None
    if _INTENT_RE.search(text):
        return {"intent": "linkedin_optimize"}
    return None


async def _optimize_linkedin_tool(args: dict) -> dict:
    profile_data = args.get("profile") or {}
    target_role = (args.get("target_role") or "").strip()
    if not target_role:
        return {"error": "target_role is required"}
    profile = LinkedInProfile.model_validate(profile_data)
    optimizer = LinkedInOptimizer()
    report = await optimizer.optimize(
        profile, target_role,
        include_headline_ab=bool(args.get("include_headline_ab", True)),
        headline_variant_count=int(args.get("headline_variant_count", 3)),
    )
    return report.model_dump()


async def _headline_ab_tool(args: dict) -> dict:
    profile_data = args.get("profile") or {}
    target_role = (args.get("target_role") or "").strip()
    n = int(args.get("n", 3))
    if not target_role:
        return {"error": "target_role is required"}
    profile = LinkedInProfile.model_validate(profile_data)
    optimizer = LinkedInOptimizer()
    variants = await optimizer.headline_ab(profile, target_role, n=n)
    return {"variants": [v.model_dump() for v in variants]}


def build_linkedin_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(AgentTool(
        name="optimize_linkedin_profile",
        description=("Rewrite headline + About for a target role and return "
                     "before/after ATS scores plus headline AB variants."),
        parameters={
            "type": "object",
            "properties": {
                "profile": {"type": "object"},
                "target_role": {"type": "string"},
                "include_headline_ab": {"type": "boolean"},
                "headline_variant_count": {"type": "integer"},
            },
            "required": ["profile", "target_role"],
        },
        fn=_optimize_linkedin_tool,
    ))
    reg.register(AgentTool(
        name="generate_linkedin_headline_ab",
        description="Generate N LinkedIn headline AB variants for a target role.",
        parameters={
            "type": "object",
            "properties": {
                "profile": {"type": "object"},
                "target_role": {"type": "string"},
                "n": {"type": "integer"},
            },
            "required": ["profile", "target_role"],
        },
        fn=_headline_ab_tool,
    ))
    return reg
