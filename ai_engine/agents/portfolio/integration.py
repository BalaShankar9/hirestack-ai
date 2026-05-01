"""S17-P3 — Portfolio site integration: intent + tools + helpers."""
from __future__ import annotations

import re
import time
from typing import Any, Dict, Optional

from ai_engine.agents.tools import AgentTool, ToolRegistry

from .schemas import PortfolioInput, PortfolioSite
from .site_generator import SiteGenerator, _ensure_input

_INTENT_RE = re.compile(
    r"\b(portfolio|personal\s+site|personal\s+website|landing\s+page)\b"
    r"|\b(generate|build|create)\b.*\b(portfolio|site|website)\b",
    re.IGNORECASE,
)


def detect_portfolio_intent(text: str) -> Optional[str]:
    if not text:
        return None
    m = _INTENT_RE.search(text)
    return m.group(0) if m else None


async def generate_portfolio_site(
    payload: Dict[str, Any],
    ai_client: Optional[Any] = None,
) -> PortfolioSite:
    return await SiteGenerator(ai_client=ai_client).generate(
        _ensure_input(payload),
    )


async def _generate_tool(**kwargs: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    site = await generate_portfolio_site(kwargs.get("input") or kwargs)
    return {
        "site": site.model_dump(),
        "latency_ms": int((time.perf_counter() - started) * 1000),
    }


def build_portfolio_tools() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        AgentTool(
            name="generate_portfolio_site",
            description=(
                "Generate a deterministic, themeable single-page portfolio "
                "site (HTML + CSS) from candidate profile data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "description": (
                            "PortfolioInput with candidate_name, headline, "
                            "summary, contact, projects, experience, skills, "
                            "theme."
                        ),
                    },
                },
                "required": ["input"],
            },
            fn=_generate_tool,
        )
    )
    return reg
