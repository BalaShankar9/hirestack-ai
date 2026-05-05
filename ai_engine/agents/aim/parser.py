"""
AIM Parser Agent \u2014 extracts directive, rubric, level, referencing style.

If parser_confidence < 0.9 the orchestrator surfaces clarification questions
and HALTS the pipeline until the user responds.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ai_engine.agents.aim.schemas import PARSER_SCHEMA
from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.client import AIClient

_PROMPT = (Path(__file__).parent / "prompts" / "parser_system.md").read_text(encoding="utf-8")
CLARIFICATION_THRESHOLD = 0.9


class AIMParserAgent(BaseAgent):
    """Structured extraction over an academic brief + (optional) rubric."""

    def __init__(self, ai_client: AIClient | None = None) -> None:
        super().__init__(
            name="aim_parser",
            system_prompt=_PROMPT,
            output_schema=PARSER_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic_ns()
        brief_text: str = context.get("brief_text") or ""
        rubric_text: str = context.get("rubric_text") or ""
        if not brief_text.strip():
            raise ValueError("aim_parser: brief_text is required")

        prompt = (
            "ASSIGNMENT BRIEF:\n"
            f"{brief_text}\n\n"
            "RUBRIC (optional, may be empty):\n"
            f"{rubric_text or '(none provided)'}\n\n"
            "Extract the structured fields per the schema. Be honest about confidence."
        )
        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            schema=self.output_schema,
            task_type="aim_parser",
            temperature=0.1,
        )
        confidence = float(result.get("confidence", 0.0))
        needs_clarification = (
            confidence < CLARIFICATION_THRESHOLD
            or not result.get("rubric_breakdown")
            or bool(result.get("clarification_questions"))
        )
        flags: list[str] = []
        if needs_clarification:
            flags.append("needs_clarification")
        if not result.get("rubric_breakdown"):
            flags.append("missing_rubric")
        return self._timed_result(
            start,
            content=result,
            quality_scores={"parser_confidence": confidence * 100},
            flags=flags,
            needs_revision=needs_clarification,
            feedback={
                "clarification_questions": result.get("clarification_questions") or [],
            } if needs_clarification else None,
            metadata={
                "agent": self.name,
                "confidence": confidence,
                "needs_clarification": needs_clarification,
            },
        )
