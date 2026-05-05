"""
AIM Recon Agent \u2014 distinction-tier strategist.

Consumes the Parser output + brief, produces the execution plan
(what-it's-really-asking, mark-loss patterns, distinction strategy,
section strategy, structure outline).
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ai_engine.agents.aim.schemas import RECON_SCHEMA
from ai_engine.agents.base import AgentResult, BaseAgent
from ai_engine.client import AIClient

_PROMPT = (Path(__file__).parent / "prompts" / "recon_system.md").read_text(encoding="utf-8")


class AIMReconAgent(BaseAgent):
    def __init__(self, ai_client: AIClient | None = None) -> None:
        super().__init__(
            name="aim_recon",
            system_prompt=_PROMPT,
            output_schema=RECON_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict[str, Any]) -> AgentResult:
        start = time.monotonic_ns()
        parsed = context.get("parsed") or {}
        brief_text: str = context.get("brief_text") or ""
        if not parsed:
            raise ValueError("aim_recon: parsed context required")

        word_count = parsed.get("word_count") or 0
        prompt = (
            "PARSED BRIEF (JSON):\n"
            f"{parsed}\n\n"
            "ORIGINAL BRIEF TEXT:\n"
            f"{brief_text}\n\n"
            f"Total word budget: {word_count or 'unspecified'}.\n"
            "Produce a distinction-tier execution plan. Word limits in the structure "
            "must be proportional to rubric weights and roughly sum to the total."
        )
        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            schema=self.output_schema,
            task_type="aim_recon",
            temperature=0.4,
        )
        confidence = float(result.get("confidence", 0.0))
        # sanity: coerce structure into well-ordered list
        structure = result.get("structure") or []
        for idx, sec in enumerate(structure):
            sec.setdefault("order_index", idx)
        result["structure"] = sorted(structure, key=lambda s: s.get("order_index", 0))

        return self._timed_result(
            start,
            content=result,
            quality_scores={"recon_confidence": confidence * 100},
            metadata={"agent": self.name, "confidence": confidence,
                      "section_count": len(result["structure"])},
        )
