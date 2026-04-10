"""
Critic Agent — rubric-based quality engine.

Outputs severity-ranked, machine-actionable issues tied to exact sections.
Decision logic is deterministic (score thresholds), LLM provides assessments.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import CRITIC_SCHEMA
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "critic_system.md"

# Deterministic revision-needed thresholds
_REVISION_THRESHOLD = 70  # Any dimension below this triggers revision
_PASS_THRESHOLD = 80  # All dimensions must be above this to pass without revision


class CriticAgent(BaseAgent):
    """Rubric engine — structured quality assessment with deterministic decisions."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="critic",
            system_prompt=system_prompt,
            output_schema=CRITIC_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context.get("draft", {})

        evaluation_mode = context.get("evaluation_mode", "single") if isinstance(context, dict) else "single"

        if evaluation_mode == "comparative":
            return await self._run_comparative(start, context)

        # Get agent memories for user preferences (if available)
        memories = context.get("agent_memories", []) if isinstance(context, dict) else []
        original_ctx = context.get("original_context", {}) if isinstance(context, dict) else {}

        prompt = (
            f"Evaluate this document draft for quality on four dimensions:\n"
            f"- Impact (0-100): quantified achievements, strong verbs, measurable results\n"
            f"- Clarity (0-100): clear writing, good structure, appropriate jargon\n"
            f"- Tone Match (0-100): matches target company culture\n"
            f"- Completeness (0-100): all sections present, no gaps\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n"
        )

        if original_ctx.get("job_title"):
            prompt += f"\nTarget Role: {original_ctx['job_title']}"
        if original_ctx.get("company"):
            prompt += f"\nTarget Company: {original_ctx['company']}"
        if memories:
            prompt += f"\n\nUser Preferences (from memory):\n{json.dumps(memories[:3], default=str)[:500]}"

        prompt += (
            "\n\nFor critical_issues, tie each issue to a specific section of the document.\n"
            "Set severity to 'critical', 'high', or 'medium'.\n"
            "Return a confidence score (0-1) for your overall assessment."
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
            schema=self.output_schema,
        )

        quality_scores = result.get("quality_scores", {})
        feedback = result.get("feedback", {})

        # Deterministic revision decision based on score thresholds
        scores = [
            quality_scores.get("impact", 0),
            quality_scores.get("clarity", 0),
            quality_scores.get("tone_match", 0),
            quality_scores.get("completeness", 0),
        ]
        needs_revision = any(s < _REVISION_THRESHOLD for s in scores)
        if not needs_revision:
            needs_revision = not all(s >= _PASS_THRESHOLD for s in scores)

        # Override LLM's needs_revision with our deterministic decision
        result["needs_revision"] = needs_revision

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=quality_scores,
            needs_revision=needs_revision,
            feedback=feedback,
        )

    async def _run_comparative(self, start: int, context: dict) -> AgentResult:
        """Compare multiple document variants (A/B Lab mode)."""
        variants = context.get("variants", [])
        variant_texts = []
        for i, v in enumerate(variants):
            content = v.content if isinstance(v, AgentResult) else v
            variant_texts.append(f"--- Variant {i+1} ---\n{json.dumps(content, indent=2)[:2000]}")

        prompt = (
            f"Compare these {len(variants)} document variants and rank them.\n\n"
            + "\n\n".join(variant_texts)
            + "\n\nReturn a confidence score (0-1) for your ranking."
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt + "\n\nYou are in COMPARATIVE mode. Rank all variants.",
            max_tokens=3000,
            temperature=0.3,
            schema=self.output_schema,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=result.get("quality_scores", {}),
        )
