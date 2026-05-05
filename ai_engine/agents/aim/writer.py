"""
AIM Writer Agent \u2014 section-locked academic writer.

Produces ONE section at a time, in claim \u2192 explanation \u2192 evidence \u2192
counterpoint \u2192 micro-conclusion blocks. Writer NEVER fabricates citations.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ai_engine.agents.aim.schemas import WRITER_SCHEMA
from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.client import AIClient

_PROMPT = (Path(__file__).parent / "prompts" / "writer_system.md").read_text(encoding="utf-8")


class AIMWriterAgent(BaseAgent):
    def __init__(self, ai_client: AIClient | None = None) -> None:
        super().__init__(
            name="aim_writer",
            system_prompt=_PROMPT,
            output_schema=WRITER_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic_ns()
        section = context.get("section") or {}
        if not section.get("title") or not section.get("word_limit"):
            raise ValueError("aim_writer: section.title and section.word_limit required")

        parsed = context.get("parsed") or {}
        recon = context.get("recon") or {}
        previous_attempt = context.get("previous_attempt")  # for revision
        reviewer_issues = context.get("reviewer_issues") or []
        directive = parsed.get("directive") or "analyse"
        academic_level = parsed.get("academic_level") or "ug"
        referencing_style = parsed.get("referencing_style") or "harvard"

        revision_block = ""
        if previous_attempt:
            revision_block = (
                "\nPREVIOUS ATTEMPT (revise it):\n"
                f"{previous_attempt}\n\n"
                "REVIEWER FEEDBACK TO ADDRESS (ranked):\n"
                f"{reviewer_issues}\n\n"
                "Apply the suggested fixes. Keep what worked. Hit the gate."
            )

        prompt = (
            f"DIRECTIVE: {directive}\n"
            f"ACADEMIC LEVEL: {academic_level}\n"
            f"REFERENCING STYLE: {referencing_style}\n\n"
            f"SECTION TITLE: {section['title']}\n"
            f"PURPOSE: {section.get('purpose', '')}\n"
            f"KEY ARGUMENT: {section.get('key_argument', '')}\n"
            f"WORD LIMIT: {section['word_limit']} (\u00b110% acceptable)\n"
            f"RUBRIC CRITERIA TO HIT: {section.get('rubric_links', [])}\n\n"
            f"DISTINCTION STRATEGY (from recon): {recon.get('distinction_strategy', '')}\n"
            f"SECTION-SPECIFIC SCORING LOGIC: {context.get('scoring_logic', '')}\n"
            f"{revision_block}\n"
            "Write the section now. Output JSON only."
        )
        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            schema=self.output_schema,
            task_type="aim_writer",
            temperature=0.5,
        )
        content_text = (result.get("content") or "").strip()
        word_count = len(content_text.split())
        result.setdefault("word_count", word_count)
        confidence = float(result.get("confidence", 0.0))

        flags: list[str] = []
        target = section["word_limit"]
        if target and (word_count < target * 0.9 or word_count > target * 1.1):
            flags.append("word_count_drift")

        return self._timed_result(
            start,
            content=result,
            quality_scores={"writer_confidence": confidence * 100},
            flags=flags,
            metadata={
                "agent": self.name,
                "confidence": confidence,
                "word_count": word_count,
                "target_words": target,
                "is_revision": bool(previous_attempt),
            },
        )
