"""
ReviewIntelSubAgent — employee review and compensation research.

Aggregates sentiment from Glassdoor, Indeed, Blind, and Levels.fyi.
Extracts interview process specifics, culture red flags, what interviewers
actually ask, and compensation reality vs posted salary.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _web_search, _search_glassdoor_reviews
from ai_engine.client import AIClient


class ReviewIntelSubAgent(SubAgent):
    """
    Review aggregation in parallel:
    - Glassdoor culture, rating, and interview reviews
    - Indeed employee reviews and common complaints
    - Blind (anonymous insider opinions on culture, pay, management)
    - Levels.fyi compensation data for this role at this company
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="review_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company_name", "") or context.get("company", "")
        job_title = context.get("job_title", "")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company_name in context")

        title_tag = f' "{job_title}"' if job_title else ""
        queries = [
            f'site:indeed.com "{company}" review culture management work life balance',
            f'"{company}"{title_tag} interview experience questions blind forum reddit',
            f'site:levels.fyi "{company}"{title_tag} salary compensation total comp',
        ]

        results = await asyncio.gather(
            _search_glassdoor_reviews(company_name=company),
            *[_web_search(q, max_results=3) for q in queries],
            return_exceptions=True,
        )

        data: dict = {"company": company, "job_title": job_title}
        evidence_items: list[dict] = []
        labels = ["glassdoor", "indeed", "interview_experience", "compensation_data"]

        sources_with_data = 0
        for label, res in zip(labels, results):
            if isinstance(res, Exception):
                data[label] = {"error": str(res)}
                continue
            data[label] = res
            snippets = (
                res.get("results", [])
                or res.get("interview_results", [])
                or res.get("review_results", [])
            ) if isinstance(res, dict) else []
            if snippets:
                sources_with_data += 1
                for item in snippets[:2]:
                    snippet = item.get("snippet", "") if isinstance(item, dict) else str(item)
                    if snippet:
                        evidence_items.append({
                            "fact": snippet[:300],
                            "source": f"review_intel:{label}",
                            "tier": "DERIVED",
                            "sub_agent": self.name,
                        })

        # Distil actual interview questions and red flags from evidence
        data["actual_interview_questions"] = [
            ev["fact"][:200]
            for ev in evidence_items
            if any(kw in ev["fact"].lower() for kw in ["asked", "question", "interview", "tell me"])
        ][:5]

        data["culture_red_flags"] = [
            ev["fact"][:200]
            for ev in evidence_items
            if any(kw in ev["fact"].lower() for kw in ["management", "toxic", "burnout", "overtime", "turnover", "culture"])
        ][:3]

        confidence = min(0.85, 0.30 + sources_with_data * 0.15)
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
