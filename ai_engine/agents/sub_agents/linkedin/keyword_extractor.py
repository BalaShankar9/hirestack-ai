"""
KeywordExtractor — deterministic Phase 1 agent.

Extracts high-value LinkedIn keywords already present in the profile
and identifies important keywords that are missing.
No LLM call — frequency heuristics.
"""
from __future__ import annotations

import re
from collections import Counter

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult

# High-value LinkedIn keywords by broad category
_HIGH_VALUE_KEYWORDS: set[str] = {
    "leadership", "strategy", "agile", "scrum", "cross-functional",
    "stakeholder", "roadmap", "roi", "revenue", "growth", "scale",
    "innovation", "transformation", "digital", "cloud", "data-driven",
    "customer", "impact", "metrics", "pipeline", "automation",
    "machine learning", "ai", "full-stack", "microservices", "saas",
    "b2b", "b2c", "startup", "enterprise", "mentorship", "coaching",
    "optimization", "compliance", "security", "performance",
    "collaboration", "communication", "problem solving",
}

_WORD_RE = re.compile(r'[a-z][a-z\-]+', re.I)


class KeywordExtractor(SubAgent):
    """Extracts present and missing high-value keywords from profile text."""

    def __init__(self, ai_client=None):
        super().__init__(name="keyword_extractor", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        profile: dict = context.get("profile_data", {})

        # Aggregate all profile text
        text_parts: list[str] = []
        text_parts.append(profile.get("title") or "")
        text_parts.append(profile.get("summary") or "")

        for exp in (profile.get("experience") or [])[:6]:
            if isinstance(exp, dict):
                text_parts.append(exp.get("title", ""))
                for ach in (exp.get("achievements") or []):
                    text_parts.append(ach)

        for s in (profile.get("skills") or []):
            if isinstance(s, dict):
                text_parts.append(s.get("name", ""))

        blob = " ".join(text_parts).lower()
        tokens = _WORD_RE.findall(blob)
        token_set = set(tokens)

        # Find present high-value keywords
        present: list[str] = sorted(kw for kw in _HIGH_VALUE_KEYWORDS if kw in blob)

        # Find missing
        missing: list[str] = sorted(kw for kw in _HIGH_VALUE_KEYWORDS if kw not in blob)

        # Top frequent tokens (for density analysis)
        counter = Counter(tokens)
        top_frequent = [w for w, _ in counter.most_common(20) if len(w) > 3]

        return SubAgentResult(
            agent_name=self.name,
            data={
                "present_keywords": present,
                "missing_keywords": missing[:15],
                "keyword_density_pct": round(len(present) / max(len(_HIGH_VALUE_KEYWORDS), 1) * 100),
                "top_frequent_words": top_frequent[:10],
            },
            confidence=0.85,
        )
