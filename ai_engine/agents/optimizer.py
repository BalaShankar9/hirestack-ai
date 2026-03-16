"""
Optimizer Agent — ATS keyword density, readability, quantified impacts.

Analyzes drafts and provides concrete optimization suggestions.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "optimizer_system.md"


class OptimizerAgent(BaseAgent):
    """Optimizes for ATS, readability, structure, and quantification."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="optimizer",
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

        jd_text = context.get("jd_text", "") if isinstance(context, dict) else ""

        prompt = (
            f"Optimize this document for ATS compatibility and readability.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"Target Job Description:\n{jd_text[:2000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=3000,
            temperature=0.3,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            suggestions=result.get("suggestions", {}),
            metadata={"agent": self.name},
        )
