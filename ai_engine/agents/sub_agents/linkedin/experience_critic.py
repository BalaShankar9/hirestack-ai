"""
ExperienceCritic — deterministic Phase 1 agent.

Analyses experience entries for LinkedIn‑readiness:
  • presence of quantified metrics
  • action-verb usage
  • achievement orientation
  • appropriate length

No LLM call — regex / keyword heuristics.
"""
from __future__ import annotations

import re

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

_ACTION_VERBS: set[str] = {
    "led", "delivered", "built", "designed", "launched", "grew", "reduced",
    "improved", "created", "managed", "drove", "increased", "achieved",
    "implemented", "developed", "scaled", "optimized", "migrated",
    "architected", "automated", "mentored", "spearheaded", "established",
    "generated", "transformed", "negotiated", "streamlined",
}

_METRIC_RE = re.compile(r'\d+\s*[%xX$]|\$\d|revenue|roi|arr|mrr|users|customers|team of', re.I)


class ExperienceCritic(SubAgent):
    """Critiques experience entries for LinkedIn-fitness."""

    def __init__(self, ai_client=None):
        super().__init__(name="experience_critic", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        profile: dict = context.get("profile_data", {})
        experience: list[dict] = profile.get("experience") or []

        critiques: list[dict] = []

        for entry in experience[:6]:
            if not isinstance(entry, dict):
                continue
            role = entry.get("title", "Unknown")
            company = entry.get("company", "Unknown")
            achievements: list[str] = entry.get("achievements") or []

            combined = " ".join(achievements).lower()
            words = combined.split()

            has_metrics = bool(_METRIC_RE.search(combined))
            action_count = sum(1 for w in words if w in _ACTION_VERBS)
            achievement_count = len(achievements)

            issues: list[str] = []
            if not achievements:
                issues.append("No achievements listed — add 2-4 bullet points with impact")
            else:
                if not has_metrics:
                    issues.append("No quantified metrics — add numbers, percentages, or dollar amounts")
                if action_count == 0:
                    issues.append("No strong action verbs — start bullets with 'Led', 'Built', 'Delivered', etc.")
                if achievement_count < 2:
                    issues.append("Only 1 bullet — add 2-4 for stronger impact")
                if any(len(a) > 200 for a in achievements):
                    issues.append("Some bullets are too long for LinkedIn — keep under 150 chars")

            critiques.append({
                "role": f"{role} at {company}",
                "achievement_count": achievement_count,
                "has_metrics": has_metrics,
                "action_verb_count": action_count,
                "issues": issues,
                "score": self._score(achievement_count, has_metrics, action_count),
            })

        avg_score = (
            round(sum(c["score"] for c in critiques) / len(critiques))
            if critiques else 0
        )

        return SubAgentResult(
            agent_name=self.name,
            data={
                "experience_critiques": critiques,
                "avg_experience_score": avg_score,
                "entries_analyzed": len(critiques),
            },
            confidence=0.85,
        )

    @staticmethod
    def _score(achievement_count: int, has_metrics: bool, action_verbs: int) -> int:
        s = 0
        s += min(achievement_count * 15, 40)
        if has_metrics:
            s += 30
        s += min(action_verbs * 10, 30)
        return min(s, 100)
