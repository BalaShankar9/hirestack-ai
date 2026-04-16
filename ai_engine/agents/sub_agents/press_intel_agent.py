"""
PressIntelSubAgent — dedicated press and PR research.

Focuses exclusively on the last 6 months: funding rounds, product launches,
layoffs, pivots, awards, and anything newsworthy. Separate from general news
research so it can be targeted at recency-critical signals.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _web_search, _search_company_news
from ai_engine.client import AIClient

# Crunchbase-style funding keywords
_FUNDING_KEYWORDS = ["Series", "funding", "raised", "investment", "valuation", "IPO", "acquisition"]


class PressIntelSubAgent(SubAgent):
    """
    Press / PR research in parallel:
    - Funding rounds (Crunchbase signals, TechCrunch, Bloomberg)
    - Product launches and major releases (last 6 months)
    - Layoffs, pivots, restructuring news
    - Awards, rankings, certifications, press recognition
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="press_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company_name", "") or context.get("company", "")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company_name in context")

        queries = [
            f'"{company}" funding raised Series investment 2024 2025 site:techcrunch.com OR site:bloomberg.com OR site:crunchbase.com',
            f'"{company}" product launch release announcement 2024 2025',
            f'"{company}" layoffs restructuring pivot news 2024 2025',
            f'"{company}" award recognition ranking certified 2024 2025',
        ]

        results = await asyncio.gather(
            _search_company_news(company_name=company),
            *[_web_search(q, max_results=3) for q in queries],
            return_exceptions=True,
        )

        data: dict = {"company": company}
        evidence_items: list[dict] = []
        labels = ["recent_news", "funding", "product_launches", "restructuring", "awards"]

        sources_with_data = 0
        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                data[label] = {"error": str(res)}
                continue
            data[label] = res
            snippets = (
                res.get("results", [])
                or res.get("funding_news", [])
                or res.get("product_news", [])
            ) if isinstance(res, dict) else []
            if snippets:
                sources_with_data += 1
                for item in snippets[:2]:
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if snippet:
                        evidence_items.append({
                            "fact": snippet[:300],
                            "source": f"press_intel:{label}",
                            "tier": "DERIVED",
                            "sub_agent": self.name,
                        })

        # Extract a clean last_6_months summary list from evidence
        data["last_6_months"] = [ev["fact"][:200] for ev in evidence_items[:5]]

        confidence = min(0.90, 0.35 + sources_with_data * 0.12)
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
