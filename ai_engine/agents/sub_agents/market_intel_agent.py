"""
MarketIntelSubAgent — salary data, industry trends, and cross-referencing.

Gathers market-level intelligence: salary benchmarks, industry trends,
and cross-references job postings from the same company.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import (
    _search_salary_data,
    _search_industry_trends,
    _cross_reference_job_postings,
)
from ai_engine.client import AIClient


class MarketIntelSubAgent(SubAgent):
    """
    Market intelligence:
    - Salary benchmarks for role + location
    - Industry trends and in-demand skills
    - Cross-reference other postings from the same company
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="market_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        job_title = context.get("job_title", "")
        company = context.get("company_name", "") or context.get("company", "")
        location = context.get("location", "")
        industry = context.get("industry", "")

        if not job_title and not company:
            return SubAgentResult(
                agent_name=self.name,
                error="Need job_title or company_name",
            )

        # Run all market research in parallel
        coros = []
        labels = []

        if job_title:
            coros.append(_search_salary_data(job_title=job_title, location=location))
            labels.append("salary_data")

        if job_title or industry:
            coros.append(_search_industry_trends(
                industry=industry or "technology",
                job_title=job_title,
            ))
            labels.append("industry_trends")

        if company:
            coros.append(_cross_reference_job_postings(
                company_name=company, job_title=job_title,
            ))
            labels.append("cross_ref_postings")

        results = await asyncio.gather(*coros, return_exceptions=True)

        data: dict = {}
        evidence_items: list[dict] = []
        sources_ok = 0

        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                data[label] = {"error": str(res)}
                continue
            data[label] = res
            sources_ok += 1
            # Extract evidence
            snippets = res.get("results", []) or res.get("other_postings", [])
            for item in (snippets[:3] if isinstance(snippets, list) else []):
                snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                if snippet:
                    evidence_items.append({
                        "fact": snippet[:300],
                        "source": f"market_intel:{label}",
                        "tier": "DERIVED",
                        "sub_agent": self.name,
                    })

        # Hiring volume insight
        cross_ref = data.get("cross_ref_postings", {})
        if cross_ref.get("hiring_volume"):
            evidence_items.append({
                "fact": f"Company hiring volume: {cross_ref['hiring_volume']}",
                "source": "market_intel:cross_ref",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })

        confidence = min(0.90, 0.40 + sources_ok * 0.18)
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
