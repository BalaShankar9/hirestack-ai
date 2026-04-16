"""
RoleIntelSubAgent — deep role-specific research.

Researches what a specific role actually involves day-to-day, career
progression paths, typical interview formats, and compensation benchmarks
for the exact title/industry/level combination.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _web_search
from ai_engine.client import AIClient


class RoleIntelSubAgent(SubAgent):
    """
    Role-specific research in parallel:
    - Day-to-day responsibilities for this exact title + industry
    - Career progression and typical next steps
    - Interview format and common question types
    - Compensation benchmarks (level-specific)
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="role_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        job_title = context.get("job_title", "")
        company = context.get("company_name", "") or context.get("company", "")
        industry = context.get("industry", "")

        if not job_title:
            return SubAgentResult(agent_name=self.name, error="No job_title in context")

        # Build targeted search queries
        industry_tag = f" {industry}" if industry else ""
        queries = [
            f'"{job_title}"{industry_tag} day-to-day responsibilities what do they actually do',
            f'"{job_title}" interview process format typical questions 2024 2025',
            f'"{job_title}"{industry_tag} salary compensation range levels',
            f'"{job_title}" career progression next role path growth',
        ]

        results = await asyncio.gather(
            *[_web_search(q, max_results=3) for q in queries],
            return_exceptions=True,
        )

        data: dict = {}
        evidence_items: list[dict] = []
        labels = ["day_to_day", "interview_format", "compensation", "career_path"]

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
                            "source": f"role_intel:{label}",
                            "tier": "DERIVED",
                            "sub_agent": self.name,
                        })

        confidence = min(0.90, 0.35 + sources_with_data * 0.15)
        return SubAgentResult(
            agent_name=self.name,
            data={
                "job_title": job_title,
                "industry": industry,
                **data,
            },
            evidence_items=evidence_items,
            confidence=confidence,
        )
