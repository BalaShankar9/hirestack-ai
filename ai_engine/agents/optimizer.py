"""
Optimizer Agent — metric-driven ATS and readability optimization.

Uses deterministic tools first (keyword overlap, readability scoring),
then lets the LLM explain and synthesize repair suggestions.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import structlog

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import OPTIMIZER_SCHEMA
from ai_engine.agents.tools import ToolRegistry, build_optimizer_tools
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.agents.optimizer")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "optimizer_system.md"


class OptimizerAgent(BaseAgent):
    """Metric-driven optimizer — deterministic tools first, LLM for synthesis."""

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        tools: Optional[ToolRegistry] = None,
    ):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="optimizer",
            system_prompt=system_prompt,
            output_schema=OPTIMIZER_SCHEMA,
            ai_client=ai_client,
        )
        self.tools = tools or build_optimizer_tools()

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context.get("draft", {})

        # JD text may be at top level or nested inside original_context
        if isinstance(context, dict):
            jd_text = context.get("jd_text", "") or context.get("original_context", {}).get("jd_text", "")
        else:
            jd_text = ""

        # Flatten content to text for deterministic tools
        draft_text = self._content_to_text(draft_content)

        # ── Deterministic tool phase ──────────────────────────────
        tool_results: dict = {}

        # Keyword overlap
        kw_tool = self.tools.get("compute_keyword_overlap")
        if kw_tool and jd_text:
            try:
                tool_results["keyword_overlap"] = await kw_tool.execute(
                    document_text=draft_text, jd_text=jd_text,
                )
            except Exception as e:
                logger.warning("optimizer_keyword_tool_failed", error=str(e))

        # Readability
        read_tool = self.tools.get("compute_readability")
        if read_tool:
            try:
                tool_results["readability"] = await read_tool.execute(text=draft_text)
            except Exception as e:
                logger.warning("optimizer_readability_tool_failed", error=str(e))

        # ── LLM synthesis phase ───────────────────────────────────
        prompt = (
            f"Optimize this document for ATS compatibility and readability.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"Target Job Description:\n{jd_text[:2000]}\n\n"
            f"## Deterministic Analysis Results\n"
            f"{json.dumps(tool_results, indent=2)[:3000]}\n\n"
            f"Use the deterministic analysis above as your ground truth for keyword\n"
            f"overlap and readability scores. Focus your suggestions on:\n"
            f"1. Missing keywords and natural insertion points\n"
            f"2. Readability improvements (target grade 8-10)\n"
            f"3. Quantification opportunities\n"
            f"Return a confidence score (0-1) for your analysis."
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=3000,
            temperature=0.3,
            schema=self.output_schema,
        )

        # Overlay deterministic metrics (don't let LLM hallucinate these)
        if "keyword_overlap" in tool_results:
            kw = tool_results["keyword_overlap"]
            result.setdefault("keyword_analysis", {})
            result["keyword_analysis"]["match_ratio"] = kw.get("match_ratio", 0)
            result["ats_score"] = round(kw.get("match_ratio", 0) * 100, 1)
        if "readability" in tool_results:
            rd = tool_results["readability"]
            result["readability_score"] = rd.get("flesch_reading_ease", 0)
            result["readability_details"] = rd

        return self._timed_result(
            start_ns=start,
            content=result,
            suggestions=result.get("suggestions", {}),
            metadata={
                "agent": self.name,
                "deterministic_ats_score": result.get("ats_score", 0),
                "deterministic_readability": result.get("readability_score", 0),
                "tools_used": list(tool_results.keys()),
            },
        )

    @staticmethod
    def _content_to_text(content: dict) -> str:
        """Flatten dict content to plain text for tool processing."""
        if isinstance(content, str):
            return content
        parts: list[str] = []
        for key, value in content.items():
            if isinstance(value, str) and len(value) > 10:
                parts.append(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, str):
                        parts.append(item)
        return "\n".join(parts) if parts else json.dumps(content)
