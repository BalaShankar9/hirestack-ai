"""
AIM Fix-My-Section Diagnostic Agent.

Diagnostic-first: identifies weak arguments / missing analysis / structural
issues. Provides up to 3 surgical before/after rewrites. Does NOT silently
rewrite the whole section.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ai_engine.agents.aim.schemas import FIX_SCHEMA
from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.client import AIClient

_PROMPT = (Path(__file__).parent / "prompts" / "fix_system.md").read_text(encoding="utf-8")


class AIMFixAgent(BaseAgent):
    def __init__(self, ai_client: AIClient | None = None) -> None:
        super().__init__(
            name="aim_fix",
            system_prompt=_PROMPT,
            output_schema=FIX_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic_ns()
        section_content: str = context.get("section_content") or ""
        if not section_content.strip():
            raise ValueError("aim_fix: section_content required")
        parsed = context.get("parsed") or {}
        section_meta = context.get("section_meta") or {}
        prompt = (
            f"DIRECTIVE: {parsed.get('directive', 'analyse')}\n"
            f"SECTION TITLE: {section_meta.get('title', '')}\n"
            f"WORD LIMIT: {section_meta.get('word_limit', 'n/a')}\n"
            f"RUBRIC: {parsed.get('rubric_breakdown', [])}\n\n"
            f"DRAFT:\n{section_content}\n\n"
            "Diagnose. Do not rewrite the whole thing."
        )
        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            schema=self.output_schema,
            task_type="aim_fix",
            temperature=0.3,
        )
        confidence = float(result.get("confidence", 0.0))
        return self._timed_result(
            start,
            content=result,
            quality_scores={"fix_confidence": confidence * 100},
            metadata={"agent": self.name, "confidence": confidence},
        )
