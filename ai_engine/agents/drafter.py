"""
Drafter Agent — wraps existing chains for first-pass generation.

The run() method delegates to the existing chain method (zero modifications).
The revise() method uses AIClient directly with a revision prompt that
includes the original draft + all agent feedback.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_REVISION_PROMPT_PATH = Path(__file__).parent / "prompts" / "drafter_revision.md"

REVISION_SYSTEM_PROMPT = (
    "You are revising a career document based on feedback from quality review agents. "
    "Maintain the document's structure and factual accuracy while addressing all feedback points. "
    "Remove any fabricated claims. Apply keyword suggestions naturally. "
    "Return the revised document in the same format as the original."
)


class DrafterAgent(BaseAgent):
    """Wraps existing chains for first-pass content generation."""

    def __init__(
        self,
        chain: Any,
        method_name: str,
        ai_client: Optional[AIClient] = None,
    ):
        super().__init__(
            name="drafter",
            system_prompt="",
            output_schema={},
            ai_client=ai_client,
        )
        self.chain = chain
        self.method_name = method_name

    async def run(self, context: dict) -> AgentResult:
        """Delegate to existing chain method — NO modifications to chain."""
        start = time.monotonic_ns()
        method = getattr(self.chain, self.method_name)

        # Build kwargs from context, matching chain method signatures
        kwargs = self._build_chain_kwargs(context)
        result = await method(**kwargs)

        # Normalize result to dict
        if isinstance(result, str):
            content = {"html": result}
        elif isinstance(result, tuple):
            content = {"valid": result[0], "details": result[1]}
        elif isinstance(result, dict):
            content = result
        else:
            content = {"result": str(result)}

        return self._timed_result(
            start_ns=start,
            content=content,
            metadata={"agent": self.name, "chain": type(self.chain).__name__, "method": self.method_name},
        )

    async def revise(self, draft: AgentResult, feedback: dict) -> AgentResult:
        """Revise using AIClient directly — does NOT modify existing chains."""
        start = time.monotonic_ns()

        revision_template = ""
        if _REVISION_PROMPT_PATH.exists():
            revision_template = _REVISION_PROMPT_PATH.read_text()

        revision_prompt = (
            f"{revision_template}\n\n"
            f"## Original Draft\n{json.dumps(draft.content, indent=2)[:5000]}\n\n"
            f"## Critic Feedback\n{json.dumps(feedback.get('critic', {}), indent=2)}\n\n"
            f"## Optimizer Suggestions\n{json.dumps(feedback.get('optimizer', {}), indent=2)}\n\n"
            f"## Fact-Check Flags\n{json.dumps(feedback.get('fact_check', []), indent=2)}\n\n"
            f"Return the revised document as JSON with the same structure as the original draft."
        )

        result = await self.ai_client.complete_json(
            system=REVISION_SYSTEM_PROMPT,
            prompt=revision_prompt,
            max_tokens=6000,
            temperature=0.4,
        )

        return self._timed_result(
            start_ns=start,
            content=result,
            metadata={"agent": self.name, "action": "revision"},
        )

    def _build_chain_kwargs(self, context: dict) -> dict:
        """Map pipeline context to chain method keyword arguments."""
        kwargs = {}
        field_map = {
            "user_profile": "user_profile",
            "job_title": "job_title",
            "company": "company",
            "jd_text": "jd_text",
            "gap_analysis": "gap_analysis",
            "resume_text": "resume_text",
            "benchmark_data": "benchmark_data",
            "strengths": "strengths",
            "company_info": "company_info",
            "projects": "projects",
        }
        for ctx_key, param_name in field_map.items():
            if ctx_key in context:
                kwargs[param_name] = context[ctx_key]

        return kwargs
