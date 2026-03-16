"""
Schema Validator Agent — final validation pass.

Checks schema compliance, format correctness, completeness, and length.
Named schema_validator.py to avoid collision with chains/validator.py.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.client import AIClient

_PROMPT_PATH = Path(__file__).parent / "prompts" / "schema_validator_system.md"


class ValidatorAgent(BaseAgent):
    """Schema compliance, format correctness, completeness, length checks."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="validator",
            system_prompt=system_prompt,
            output_schema={},
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context

        prompt = (
            f"Validate this document for schema compliance, format, and completeness.\n\n"
            f"Content:\n{json.dumps(draft_content, indent=2)[:5000]}\n"
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=1500,
            temperature=0.2,
        )

        valid = result.get("valid", True)
        issues = result.get("issues", [])

        # Pass through the content if valid
        if valid:
            result["content"] = draft_content

        return self._timed_result(
            start_ns=start,
            content=result,
            flags=[f"validation_issue: {i}" for i in issues],
            metadata={"agent": self.name, "valid": valid},
        )
