"""
Optimizer specialist sub-agents — 2 parallel specialists.

Splits optimization into ATS keyword analysis and readability analysis,
each running independently for faster evaluation.
"""
from __future__ import annotations

import json
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.agents.tools import _compute_keyword_overlap, _compute_readability
from ai_engine.client import AIClient


class ATSOptimizerSubAgent(SubAgent):
    """ATS keyword coverage analysis and optimization suggestions."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="optimizer:ats", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        draft_content = context.get("draft_content", {})
        draft_text = self._content_to_text(draft_content)
        jd_text = context.get("jd_text", "")

        if not draft_text or not jd_text:
            return SubAgentResult(
                agent_name=self.name,
                error="Need both draft and JD text",
            )

        # Deterministic keyword overlap
        overlap = await _compute_keyword_overlap(
            document_text=draft_text, jd_text=jd_text,
        )

        match_ratio = overlap.get("overlap_pct", 0) / 100.0
        missing = overlap.get("missing_keywords", [])

        # LLM pass for targeted insertion suggestions
        suggestions = []
        if missing:
            try:
                prompt = (
                    f"The document is missing these JD keywords: {', '.join(missing[:12])}\n"
                    f"Draft excerpt: {draft_text[:2000]}\n\n"
                    f"Suggest natural insertions. Return JSON: {{"
                    f'"suggestions": [{{"keyword": "...", "insertion": "...",'
                    f' "section": "...", "priority": "must-have|nice-to-have"}}]}}'
                )
                result = await self.ai_client.complete_json(
                    system="You are an ATS optimization specialist. Suggest keyword insertions that sound natural.",
                    prompt=prompt,
                    max_tokens=1000,
                    temperature=0.3,
                    task_type="optimization",
                )
                suggestions = result.get("suggestions", [])
            except Exception:
                pass  # Fall back to just the deterministic analysis

        ats_score = int(match_ratio * 100)
        return SubAgentResult(
            agent_name=self.name,
            data={
                "ats_score": ats_score,
                "match_ratio": match_ratio,
                "missing_keywords": missing,
                "suggestions": suggestions,
                "keyword_overlap": overlap,
            },
            confidence=0.85,
        )

    @staticmethod
    def _content_to_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            parts = []
            for v in content.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        parts.append(str(item))
            return " ".join(parts)
        return str(content)


class ReadabilityOptimizerSubAgent(SubAgent):
    """Readability analysis and improvement suggestions."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="optimizer:readability", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        draft_content = context.get("draft_content", {})
        draft_text = self._content_to_text(draft_content)

        if not draft_text:
            return SubAgentResult(agent_name=self.name, error="No draft content")

        # Deterministic readability analysis
        readability = await _compute_readability(text=draft_text)

        flesch = readability.get("flesch_reading_ease", 50)
        grade = readability.get("grade_level", 12)
        passive_count = readability.get("passive_voice_count", 0)
        long_sentences = readability.get("long_sentences", 0)

        # Determine quality band
        if 55 <= flesch <= 75 and grade <= 12:
            band = "optimal"
        elif flesch >= 45:
            band = "acceptable"
        else:
            band = "needs_improvement"

        # LLM pass for specific improvement suggestions if needed
        suggestions = []
        if band == "needs_improvement" or passive_count > 3 or long_sentences > 2:
            try:
                prompt = (
                    f"Readability analysis:\n"
                    f"- Flesch score: {flesch} (target: 55-75)\n"
                    f"- Grade level: {grade} (target: ≤12)\n"
                    f"- Passive voice: {passive_count} instances\n"
                    f"- Long sentences: {long_sentences}\n\n"
                    f"Draft excerpt: {draft_text[:2000]}\n\n"
                    f"Suggest specific readability improvements. Return JSON: {{"
                    f'"suggestions": [{{"issue": "...", "original": "...", "revised": "...", "impact": "high|medium"}}]}}'
                )
                result = await self.ai_client.complete_json(
                    system="You are a readability specialist. Improve clarity without changing meaning.",
                    prompt=prompt,
                    max_tokens=1000,
                    temperature=0.3,
                    task_type="optimization",
                )
                suggestions = result.get("suggestions", [])
            except Exception:
                pass

        return SubAgentResult(
            agent_name=self.name,
            data={
                "readability_score": flesch,
                "grade_level": grade,
                "passive_voice_count": passive_count,
                "long_sentences": long_sentences,
                "quality_band": band,
                "suggestions": suggestions,
                "readability_details": readability,
            },
            confidence=0.85,
        )

    @staticmethod
    def _content_to_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            parts = []
            for v in content.values():
                if isinstance(v, str):
                    parts.append(v)
                elif isinstance(v, list):
                    for item in v:
                        parts.append(str(item))
            return " ".join(parts)
        return str(content)
