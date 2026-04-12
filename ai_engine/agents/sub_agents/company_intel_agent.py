"""
CompanyIntelSubAgent — deep company research via web tools.

Gathers Glassdoor reviews, LinkedIn insights, recent news, competitor
landscape, and engineering blog/OSS activity — all in parallel.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import (
    _search_company_info,
    _search_glassdoor_reviews,
    _search_linkedin_insights,
    _search_company_news,
    _search_competitor_landscape,
    _search_tech_blog,
)
from ai_engine.client import AIClient


class CompanyIntelSubAgent(SubAgent):
    """
    All company-focused web research in parallel:
    - General company info
    - Glassdoor reviews (culture, interview process)
    - LinkedIn insights (career paths, hiring patterns)
    - Recent news (funding, acquisitions)
    - Competitor landscape
    - Engineering blog / OSS activity
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="company_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company_name", "")
        if not company:
            # Try extracting from jd_text
            company = context.get("company", "")
        if not company:
            return SubAgentResult(agent_name=self.name, error="No company_name in context")

        job_title = context.get("job_title", "")
        industry = context.get("industry", "")

        # Fan out ALL company research in parallel
        results = await asyncio.gather(
            _search_company_info(company_name=company),
            _search_glassdoor_reviews(company_name=company),
            _search_linkedin_insights(company_name=company, job_title=job_title),
            _search_company_news(company_name=company),
            _search_competitor_landscape(company_name=company, industry=industry),
            _search_tech_blog(company_name=company),
            return_exceptions=True,
        )

        labels = [
            "general_info", "glassdoor", "linkedin",
            "news", "competitors", "tech_blog",
        ]
        data: dict = {}
        evidence_items: list[dict] = []
        sources_with_data = 0

        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                data[label] = {"error": str(res)}
                continue
            data[label] = res
            if res.get("has_data", False) or (isinstance(res, dict) and res.get("results")):
                sources_with_data += 1
                # Extract evidence from results
                snippets = (
                    res.get("results", [])
                    or res.get("interview_results", [])
                    or res.get("blog_results", [])
                    or res.get("funding_news", [])
                )
                for item in (snippets[:3] if isinstance(snippets, list) else []):
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if snippet:
                        evidence_items.append({
                            "fact": snippet[:300],
                            "source": f"company_intel:{label}",
                            "tier": "DERIVED",
                            "sub_agent": self.name,
                        })

        # Confidence based on how many sources returned data
        confidence = min(0.95, 0.40 + sources_with_data * 0.10)

        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
