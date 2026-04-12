"""
JDAnalystSubAgent — deep job description analysis.

Performs deterministic parsing, sentiment analysis, and an LLM-driven
requirements-priority extraction in one shot.
"""
from __future__ import annotations

from typing import Any, Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import (
    _parse_jd,
    _analyze_jd_sentiment,
    _compute_keyword_overlap,
)
from ai_engine.client import AIClient


class JDAnalystSubAgent(SubAgent):
    """
    Extracts everything knowable from the job description alone:
    - Keyword extraction + frequency
    - Sentiment/red-flag analysis
    - Keyword overlap with user profile (when available)
    - Section structure analysis
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="jd_analyst", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        jd_text = context.get("jd_text", "")
        if not jd_text:
            return SubAgentResult(agent_name=self.name, error="No jd_text in context")

        # Run deterministic tools
        parse_result = await _parse_jd(jd_text=jd_text)
        sentiment = await _analyze_jd_sentiment(jd_text=jd_text)

        # Keyword overlap with profile if available
        overlap: dict[str, Any] = {}
        user_profile = context.get("user_profile", {})
        profile_text = user_profile.get("resume_text", "") or user_profile.get("summary", "")
        if profile_text:
            overlap = await _compute_keyword_overlap(
                document_text=profile_text, jd_text=jd_text
            )

        # Build evidence items (for ledger)
        evidence_items: list[dict] = []
        for kw in parse_result.get("top_keywords", [])[:15]:
            evidence_items.append({
                "fact": f"JD requires: {kw}",
                "source": "parse_jd",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })
        if sentiment.get("red_flags"):
            evidence_items.append({
                "fact": f"JD red flags: {', '.join(sentiment['red_flags'])}",
                "source": "jd_sentiment",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })

        data = {
            "parsed_jd": parse_result,
            "sentiment": sentiment,
            "keyword_overlap": overlap,
        }

        confidence = 0.85 if parse_result.get("top_keywords") else 0.50
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
