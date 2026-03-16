"""
Critic Agent — quality review and scoring.

Evaluates drafts on impact, clarity, tone match, and completeness.
Decides whether revision is needed based on score thresholds.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "critic_system.md"


class CriticAgent(BaseAgent):
    """Reviews drafts for quality, tone, completeness, consistency."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="critic",
            system_prompt=system_prompt,
            output_schema={},
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

        prompt = (
            f"Evaluate this document draft for quality.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=2048,
            temperature=0.3,
        )

        quality_scores = result.get("quality_scores", {})
        needs_revision = result.get("needs_revision", False)
        feedback = result.get("feedback", {})

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
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt + "\n\nYou are in COMPARATIVE mode. Rank all variants.",
            max_tokens=3000,
            temperature=0.3,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            quality_scores=result.get("quality_scores", {}),
        )
