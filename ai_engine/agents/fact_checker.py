"""
Fact-Checker Agent — source verification with three-tier classification.

Classifies every claim as verified, enhanced, or fabricated.
Enhancement (strategic reframing) is allowed; fabrication is not.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "fact_checker_system.md"


class FactCheckerAgent(BaseAgent):
    """Cross-references every claim against source profile data."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="fact_checker",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        """Accepts a dict with 'draft' (the content to verify) and 'source' (the profile data).
        Also accepts an AgentResult directly (draft content extracted from .content).
        The orchestrator passes: fact_checker.run({"draft": draft, "source": original_context})
        """
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
            user_profile = {}
        else:
            draft_obj = context.get("draft")
            if isinstance(draft_obj, AgentResult):
                draft_content = draft_obj.content
            else:
                draft_content = context.get("content") or context.get("draft", {})
            source_data = context.get("source", context)
            user_profile = source_data.get("user_profile", {})

        prompt = (
            f"Verify every claim in this document against the user's profile data.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"Source Profile Data:\n{json.dumps(user_profile, indent=2)[:3000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=4000,
            temperature=0.2,
        )

        summary = result.get("summary", {})
        fabricated = result.get("fabricated_claims", [])
        flags = [f"fabricated: {c.get('text', '')}" for c in fabricated]

        return self._timed_result(
            start_ns=start,
            content=result,
            flags=flags,
            metadata={
                "agent": self.name,
                "verified": summary.get("verified", 0),
                "enhanced": summary.get("enhanced", 0),
                "fabricated": summary.get("fabricated", 0),
            },
        )
