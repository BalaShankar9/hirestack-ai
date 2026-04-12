"""
Critic specialist sub-agents — 4 parallel evaluators.

Each focuses on ONE quality dimension so evaluations can run concurrently
and provide deeper analysis than a single monolithic pass.
"""
from __future__ import annotations

import json
from typing import Optional

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient


class _CriticDimensionSubAgent(SubAgent):
    """Base for dimension-specific critic sub-agents."""

    dimension: str = ""
    evaluation_prompt: str = ""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name=f"critic:{self.dimension}", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        draft_content = context.get("draft_content", {})
        draft_text = json.dumps(draft_content)[:4000] if draft_content else ""
        if not draft_text:
            return SubAgentResult(agent_name=self.name, error="No draft content")

        jd_text = context.get("jd_text", "")
        company = context.get("company_name", "") or context.get("company", "")

        prompt = (
            f"Evaluate this draft on the '{self.dimension}' dimension ONLY.\n\n"
            f"## Draft\n{draft_text}\n\n"
            f"## Job Description\n{jd_text[:2000]}\n\n"
            f"## Company\n{company}\n\n"
            f"{self.evaluation_prompt}\n\n"
            f"Return JSON: {{"
            f'"score": 0-100, '
            f'"issues": [{{"severity": "critical|high|medium", "section": "...", '
            f'"issue": "...", "suggestion": "...", "expected_gain": 0-15}}], '
            f'"summary": "..."}}'
        )

        try:
            result = await self.ai_client.complete_json(
                system=(
                    f"You are a specialist document critic focusing ONLY on '{self.dimension}'. "
                    "Provide specific, actionable feedback with severity ratings."
                ),
                prompt=prompt,
                max_tokens=1200,
                temperature=0.2,
                task_type="critique",
            )
        except Exception as exc:
            return SubAgentResult(agent_name=self.name, error=str(exc))

        score = result.get("score", 50)
        issues = result.get("issues", [])
        for issue in issues:
            issue["dimension"] = self.dimension

        return SubAgentResult(
            agent_name=self.name,
            data={
                "dimension": self.dimension,
                "score": score,
                "issues": issues,
                "summary": result.get("summary", ""),
            },
            confidence=0.80,
        )


class ImpactCriticSubAgent(_CriticDimensionSubAgent):
    dimension = "impact"
    evaluation_prompt = (
        "Focus on: quantified achievements, strong action verbs, measurable results, "
        "specific outcomes. Does this draft demonstrate tangible value? Are there vague "
        "claims that could be quantified? Are achievements specific enough?"
    )


class ClarityCriticSubAgent(_CriticDimensionSubAgent):
    dimension = "clarity"
    evaluation_prompt = (
        "Focus on: clear writing, logical structure, appropriate jargon level, "
        "sentence length, paragraph flow. Is the document easy to scan? Are there "
        "confusing sentences, redundancies, or unclear references?"
    )


class ToneMatchCriticSubAgent(_CriticDimensionSubAgent):
    dimension = "tone_match"
    evaluation_prompt = (
        "Focus on: alignment with target company culture, appropriate formality level, "
        "consistency of voice throughout, industry-appropriate language. Does the tone "
        "match what this company would expect from candidates?"
    )


class CompletenessCriticSubAgent(_CriticDimensionSubAgent):
    dimension = "completeness"
    evaluation_prompt = (
        "Focus on: all required sections present, no gaps in coverage, JD requirements "
        "addressed, education/certifications included where relevant. Are there missing "
        "sections? Does the document address all key JD requirements?"
    )
