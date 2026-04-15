"""
FounderIntelSubAgent — leadership & hiring manager research.

Researches the CEO, CTO, or founder of the target company — their background,
public talks, blog posts, LinkedIn articles, and stated values. If a hiring
manager is named in the JD, researches them too. This intel is gold for
personalizing cover letters.
"""
from __future__ import annotations

import asyncio
import re
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _web_search
from ai_engine.client import AIClient


def _extract_hiring_manager(jd_text: str) -> str:
    """Try to extract a named hiring manager or contact from the JD text."""
    patterns = [
        r"(?:reports to|hiring manager|contact|reach out to)[:\s]+([A-Z][a-z]+ [A-Z][a-z]+)",
        r"([A-Z][a-z]+ [A-Z][a-z]+),?\s+(?:VP|Director|Head|Chief|Manager|Lead)",
    ]
    for pat in patterns:
        m = re.search(pat, jd_text)
        if m:
            return m.group(1)
    return ""


class FounderIntelSubAgent(SubAgent):
    """
    Leadership research in parallel:
    - CEO / CTO / Founder background and public profile
    - Public talks, articles, stated values and interests
    - Hiring manager research (if named in JD)
    - Leadership team visible from LinkedIn or press
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="founder_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company_name", "") or context.get("company", "")
        jd_text = context.get("jd_text", "")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company_name in context")

        hiring_manager = _extract_hiring_manager(jd_text)

        queries = [
            f'"{company}" CEO founder background story blog LinkedIn',
            f'"{company}" CEO CTO leadership team interview talk podcast beliefs',
            f'"{company}" founder values mission culture vision statement',
        ]
        if hiring_manager:
            queries.append(f'"{hiring_manager}" {company} background LinkedIn career')

        results = await asyncio.gather(
            *[_web_search(q, max_results=3) for q in queries],
            return_exceptions=True,
        )

        data: dict = {"company": company}
        if hiring_manager:
            data["hiring_manager_name"] = hiring_manager

        evidence_items: list[dict] = []
        labels = ["ceo_background", "leadership_beliefs", "founder_values"]
        if hiring_manager:
            labels.append("hiring_manager")

        sources_with_data = 0
        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                data[label] = {"error": str(res)}
                continue
            data[label] = res
            snippets = res.get("results", []) if isinstance(res, dict) else []
            if snippets:
                sources_with_data += 1
                for item in snippets[:2]:
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if snippet:
                        evidence_items.append({
                            "fact": snippet[:300],
                            "source": f"founder_intel:{label}",
                            "tier": "DERIVED",
                            "sub_agent": self.name,
                        })

        # Build talking_points placeholder — will be enriched by company intel synthesis
        data["talking_points"] = [
            ev["fact"][:150] for ev in evidence_items[:3]
        ]

        confidence = min(0.85, 0.30 + sources_with_data * 0.15)
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
