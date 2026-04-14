"""
ProfileMatchSubAgent — extract and match user profile evidence against the JD.

Runs extract_profile_evidence, then computes keyword overlap and gap
analysis between the profile and the parsed JD.
"""
from __future__ import annotations

from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _extract_profile_evidence, _compute_keyword_overlap
from ai_engine.client import AIClient


class ProfileMatchSubAgent(SubAgent):
    """
    Profile-focused analysis:
    - Extract structured evidence (skills, companies, titles, education, certs)
    - Compute keyword overlap with JD
    - Identify skill gaps and strengths
    """

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="profile_match", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        if not user_profile:
            return SubAgentResult(
                agent_name=self.name,
                data={"note": "No user_profile in context — skipped"},
                confidence=0.30,
            )

        # Extract structured evidence from profile
        profile_evidence = await _extract_profile_evidence(user_profile=user_profile)

        # Compute keyword overlap with JD
        jd_text = context.get("jd_text", "")
        overlap: dict = {}
        if jd_text:
            profile_text = user_profile.get("resume_text", "") or user_profile.get("summary", "")
            if profile_text:
                overlap = await _compute_keyword_overlap(
                    document_text=profile_text, jd_text=jd_text
                )

        # Build evidence items
        evidence_items: list[dict] = []
        for skill in profile_evidence.get("skills", [])[:20]:
            evidence_items.append({
                "fact": f"User has skill: {skill}",
                "source": "profile",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })
        for cert in profile_evidence.get("certifications", []):
            evidence_items.append({
                "fact": f"User has certification: {cert}",
                "source": "profile",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })
        for exp in profile_evidence.get("companies_and_titles", [])[:5]:
            evidence_items.append({
                "fact": f"User worked at: {exp}",
                "source": "profile",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })

        # Calculate match quality
        match_pct = overlap.get("overlap_pct", 0) if overlap else 0
        gap_keywords = overlap.get("missing_keywords", []) if overlap else []

        data = {
            "profile_evidence": profile_evidence,
            "keyword_overlap": overlap,
            "match_percentage": match_pct,
            "gap_keywords": gap_keywords[:20],
        }

        confidence = 0.85 if profile_evidence.get("skills") else 0.50
        return SubAgentResult(
            agent_name=self.name,
            data=data,
            evidence_items=evidence_items,
            confidence=confidence,
        )
