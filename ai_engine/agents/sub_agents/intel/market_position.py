"""
MarketPositionAgent — market, competitor, and salary intelligence.

Uses the existing research tools (company info, Glassdoor, LinkedIn, news,
competitors) to gather market-level intelligence about the company.
"""
from __future__ import annotations

import asyncio
from typing import Any, Optional

import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import (
    _search_company_info,
    _search_glassdoor_reviews,
    _search_linkedin_insights,
    _search_company_news,
    _search_competitor_landscape,
    _search_tech_blog,
    _search_salary_data,
    _search_industry_trends,
    _cross_reference_job_postings,
)
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.market")


class MarketPositionAgent(SubAgent):
    """Market intelligence: competitors, salary, Glassdoor, LinkedIn, news, trends."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="market_position", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company", "") or context.get("company_name", "")
        job_title = context.get("job_title", "")
        location = context.get("location", "")
        industry = context.get("industry", "")
        on_event = context.get("on_event")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company name")

        if on_event:
            await _emit(on_event, f"Gathering market intelligence for {company}…", "running", "market")

        # Fan out ALL market research in parallel
        tasks = {
            "company_info": _search_company_info(company_name=company),
            "glassdoor": _search_glassdoor_reviews(company_name=company),
            "linkedin": _search_linkedin_insights(company_name=company, job_title=job_title),
            "news": _search_company_news(company_name=company),
            "competitors": _search_competitor_landscape(company_name=company, industry=industry),
            "tech_blog": _search_tech_blog(company_name=company),
        }

        if job_title:
            tasks["salary"] = _search_salary_data(job_title=job_title, location=location)
        if job_title or industry:
            tasks["trends"] = _search_industry_trends(industry=industry or "technology", job_title=job_title)
        if company:
            tasks["cross_ref"] = _cross_reference_job_postings(company_name=company, job_title=job_title)

        labels = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)

        data: dict[str, Any] = {}
        evidence_items: list[dict] = []
        sources_with_data = 0

        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                data[label] = {"error": str(res)[:200]}
                continue
            data[label] = res
            # Check if there's meaningful data
            has_data = False
            if isinstance(res, dict):
                has_data = res.get("has_data", False) or bool(res.get("results") or res.get("interview_results") or
                                                              res.get("blog_results") or res.get("funding_news") or
                                                              res.get("other_postings"))
            if has_data:
                sources_with_data += 1
                # Extract evidence from results
                snippets = (
                    res.get("results", []) or res.get("interview_results", []) or
                    res.get("blog_results", []) or res.get("funding_news", []) or
                    res.get("other_postings", [])
                )
                for item in (snippets[:3] if isinstance(snippets, list) else []):
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if snippet:
                        evidence_items.append({
                            "fact": snippet[:300],
                            "source": f"market:{label}",
                            "tier": "DERIVED",
                            "sub_agent": self.name,
                        })

        # Hiring volume from cross-ref
        cross_ref = data.get("cross_ref", {})
        if isinstance(cross_ref, dict) and cross_ref.get("hiring_volume"):
            evidence_items.append({
                "fact": f"Hiring volume: {cross_ref['hiring_volume']}",
                "source": "market:cross_ref",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })

        if on_event:
            await _emit(
                on_event,
                f"Market intel gathered from {sources_with_data}/{len(labels)} sources.",
                "completed", "market",
                metadata={"sources_with_data": sources_with_data, "total_sources": len(labels)},
            )

        confidence = min(0.95, 0.30 + sources_with_data * 0.08)

        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )


async def _emit(callback, message, status, source, url=None, metadata=None):
    payload: dict[str, Any] = {"stage": "recon", "status": status, "message": message, "source": source}
    if url:
        payload["url"] = url
    if metadata:
        payload["metadata"] = metadata
    try:
        maybe = callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass
