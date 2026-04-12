"""
FactChecker specialist sub-agents — 3 parallel specialists.

Splits fact-checking into claim extraction, evidence matching, and
cross-reference verification for deeper accuracy analysis.
"""
from __future__ import annotations

import json
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import (
    _extract_claims,
    _extract_profile_evidence,
    _match_claims_to_evidence,
)
from ai_engine.client import AIClient


class ClaimExtractorSubAgent(SubAgent):
    """Extract and categorize claims from a draft document."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="fact_check:claim_extractor", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        draft_content = context.get("draft_content", {})
        draft_text = self._content_to_text(draft_content)
        if not draft_text:
            return SubAgentResult(agent_name=self.name, error="No draft content")

        claims = await _extract_claims(document_text=draft_text)
        claim_list = claims.get("claims", [])

        return SubAgentResult(
            agent_name=self.name,
            data={
                "claims": claim_list,
                "total_claims": len(claim_list),
                "categories": self._categorize(claim_list),
            },
            confidence=0.85,
        )

    @staticmethod
    def _categorize(claims: list) -> dict:
        cats: dict[str, int] = {}
        for c in claims:
            cat = c.get("category", "general") if isinstance(c, dict) else "general"
            cats[cat] = cats.get(cat, 0) + 1
        return cats

    @staticmethod
    def _content_to_text(content: dict) -> str:
        if isinstance(content, str):
            return content
        parts = []
        for v in content.values():
            if isinstance(v, str):
                parts.append(v)
            elif isinstance(v, list):
                for item in v:
                    parts.append(str(item))
        return " ".join(parts)


class EvidenceMatcherSubAgent(SubAgent):
    """Match extracted claims against user profile evidence."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="fact_check:evidence_matcher", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        user_profile = context.get("user_profile", {})
        claims = context.get("claims", [])

        if not user_profile:
            return SubAgentResult(agent_name=self.name, error="No user_profile")
        if not claims:
            return SubAgentResult(
                agent_name=self.name,
                data={"match_results": [], "note": "No claims to match"},
                confidence=0.50,
            )

        # Extract structured evidence
        evidence = await _extract_profile_evidence(user_profile=user_profile)

        # Match claims to evidence
        match_results = await _match_claims_to_evidence(
            claims=claims, evidence=evidence,
        )

        matched = match_results.get("matched", [])
        unmatched = match_results.get("unmatched", [])

        evidence_items: list[dict] = []
        for m in matched:
            evidence_items.append({
                "fact": f"Verified: {m.get('claim', '')[:200]}",
                "source": "profile_evidence",
                "tier": "VERBATIM",
                "sub_agent": self.name,
            })

        total = len(matched) + len(unmatched)
        accuracy = len(matched) / total if total else 0.5

        return SubAgentResult(
            agent_name=self.name,
            data={
                "matched": matched,
                "unmatched": unmatched,
                "match_rate": accuracy,
                "total_claims": total,
            },
            evidence_items=evidence_items,
            confidence=accuracy,
        )


class CrossRefCheckerSubAgent(SubAgent):
    """Cross-reference unmatched claims via LLM reasoning."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="fact_check:cross_ref", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        unmatched = context.get("unmatched_claims", [])
        user_profile = context.get("user_profile", {})

        if not unmatched:
            return SubAgentResult(
                agent_name=self.name,
                data={"classifications": [], "note": "No unmatched claims to classify"},
                confidence=0.90,
            )

        # Use LLM to classify ambiguous claims
        profile_summary = json.dumps(user_profile)[:3000] if user_profile else "N/A"
        claims_text = "\n".join(
            f"- {c.get('text', c) if isinstance(c, dict) else str(c)}"
            for c in unmatched[:15]
        )

        prompt = (
            f"Classify each unmatched claim as: verified (inferrable from profile), "
            f"inferred (reasonable extrapolation), embellished (reframing real experience), "
            f"or fabricated (no basis).\n\n"
            f"## User Profile\n{profile_summary}\n\n"
            f"## Unmatched Claims\n{claims_text}\n\n"
            f'Return JSON: {{"classifications": [{{"claim": "...", '
            f'"classification": "verified|inferred|embellished|fabricated", '
            f'"reasoning": "...", "confidence": 0.0-1.0}}]}}'
        )

        try:
            result = await self.ai_client.complete_json(
                system=(
                    "You are a rigorous fact-checking specialist. Classify claims by comparing "
                    "them to the user's actual profile. 'fabricated' means absolutely NO basis."
                ),
                prompt=prompt,
                max_tokens=1500,
                temperature=0.2,
                task_type="critique",
            )
        except Exception as exc:
            return SubAgentResult(agent_name=self.name, error=str(exc))

        classifications = result.get("classifications", [])
        fabricated = [c for c in classifications if c.get("classification") == "fabricated"]

        evidence_items: list[dict] = []
        for fab in fabricated:
            evidence_items.append({
                "fact": f"Fabricated claim: {fab.get('claim', '')[:200]}",
                "source": "cross_ref_check",
                "tier": "DERIVED",
                "sub_agent": self.name,
            })

        return SubAgentResult(
            agent_name=self.name,
            data={
                "classifications": classifications,
                "fabricated_count": len(fabricated),
            },
            evidence_items=evidence_items,
            confidence=0.75,
        )
