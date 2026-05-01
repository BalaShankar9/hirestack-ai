"""S18 — Recon Swarm v2 integration: intent + tools."""
from __future__ import annotations

import re
from typing import Any, Dict, Optional

from ai_engine.agents.tools import AgentTool, ToolRegistry

from .coordinator_v2 import run_recon_swarm
from .schemas import ReconSwarmReport, ReconSwarmRequest

_INTENT_RE = re.compile(
    r"\b(deep|elite|full|comprehensive)\b.*\b(recon|research|intel|profile)\b"
    r"|\b(intel|recon)\s+swarm\b"
    r"|\bbuild\s+(a\s+)?company\s+(profile|dossier)\b",
    re.IGNORECASE,
)


def detect_recon_swarm_intent(text: str) -> Optional[str]:
    if not text:
        return None
    m = _INTENT_RE.search(text)
    return m.group(0) if m else None


async def _recon_swarm_tool(**kwargs: Any) -> Dict[str, Any]:
    payload = kwargs.get("input") or kwargs
    if isinstance(payload, ReconSwarmRequest):
        req = payload
    else:
        req = ReconSwarmRequest(**(payload or {}))
    report: ReconSwarmReport = await run_recon_swarm(req)
    return {"report": report.model_dump()}


def build_recon_swarm_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        AgentTool(
            name="run_recon_swarm",
            description=(
                "Run the 5-layer Deep Intelligence Engine: source "
                "discovery, deep extraction, structured fusion, and "
                "application weaponization. Returns CompanyIntelV2 + "
                "ApplicationKit + provider results + cache metadata."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "description": (
                            "ReconSwarmRequest with company (required), "
                            "role_target, candidate_skills, "
                            "candidate_values, website, budget_seconds, "
                            "use_cache."
                        ),
                    },
                },
                "required": ["input"],
            },
            fn=_recon_swarm_tool,
        )
    )
    return reg
