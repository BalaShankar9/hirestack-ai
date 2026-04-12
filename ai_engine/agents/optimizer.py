"""
Optimizer Agent — metric-driven ATS and readability optimization.

Uses deterministic tools first (keyword overlap, readability scoring),
then lets the LLM produce constrained rewrite suggestions anchored to
actual metric gaps. Deterministic scores are NEVER overridden by LLM.

v2: JD-requirement-aware suggestions, constrained insertion points,
    factual truth preservation, per-keyword priority ordering.
v3: Parallel sub-agent evaluation mode (ATS ∥ Readability).
"""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Optional

import structlog

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import OPTIMIZER_SCHEMA
from ai_engine.agents.sub_agents.base import SubAgentCoordinator
from ai_engine.agents.sub_agents.optimizer_specialists import (
    ATSOptimizerSubAgent,
    ReadabilityOptimizerSubAgent,
)
from ai_engine.agents.tools import ToolRegistry, build_optimizer_tools
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.agents.optimizer")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "optimizer_system.md"

# Target readability band for career documents
_IDEAL_FLESCH_MIN = 55
_IDEAL_FLESCH_MAX = 75
_MAX_GRADE = 12


class OptimizerAgent(BaseAgent):
    """Metric-driven optimizer — deterministic tools first, LLM for constrained synthesis.

    v2 improvements:
    - Per-keyword priority ordering (must-have vs nice-to-have from JD)
    - Constrained insertion suggestions (location-specific, context-aware)
    - Factual truth preservation (suggestions never fabricate claims)
    - Readability improvement plan with specific sentence-level fixes
    """

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

        # ── Build targeted improvement plan ───────────────────────
        improvement_plan: list[str] = []
        kw_data = tool_results.get("keyword_overlap", {})
        rd_data = tool_results.get("readability", {})

        missing_kws = kw_data.get("missing_from_document", [])
        if missing_kws:
            improvement_plan.append(
                f"KEYWORD GAP: {len(missing_kws)} JD keywords missing from document. "
                f"Top missing: {', '.join(missing_kws[:8])}. "
                f"For each, suggest a NATURAL insertion point in an existing sentence."
            )

        flesch = rd_data.get("flesch_reading_ease", 70)
        grade = rd_data.get("grade_level", 8)
        if flesch < _IDEAL_FLESCH_MIN:
            improvement_plan.append(
                f"READABILITY: Flesch score {flesch} is below ideal ({_IDEAL_FLESCH_MIN}-{_IDEAL_FLESCH_MAX}). "
                f"Grade level {grade}. Break long sentences, reduce passive voice "
                f"({rd_data.get('passive_voice_count', 0)} instances found)."
            )
        elif flesch > _IDEAL_FLESCH_MAX:
            improvement_plan.append(
                f"READABILITY: Flesch score {flesch} is above ideal — language may be too simple. "
                f"Add some technical specificity to demonstrate domain expertise."
            )

        long_sentences = rd_data.get("long_sentences", 0)
        if long_sentences > 0:
            improvement_plan.append(
                f"SENTENCE LENGTH: {long_sentences} sentences exceed 25 words. "
                f"Split them or convert to bullet points."
            )

        # ── LLM synthesis phase ───────────────────────────────────
        prompt = (
            f"Optimize this document for ATS compatibility and readability.\n\n"
            f"Draft Content:\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"Target Job Description:\n{jd_text[:2000]}\n\n"
            f"## Deterministic Analysis Results (ground truth — do NOT contradict)\n"
            f"{json.dumps(tool_results, indent=2)[:3000]}\n\n"
            f"## Improvement Plan\n"
            + "\n".join(f"- {item}" for item in improvement_plan)
            + "\n\n"
            f"## RULES\n"
            f"1. For each missing keyword, provide a SPECIFIC insertion suggestion:\n"
            f"   which section, which sentence, and exactly how to naturally weave it in.\n"
            f"2. NEVER fabricate achievements, metrics, or credentials.\n"
            f"   Suggestions must only HIGHLIGHT or REWORD existing content.\n"
            f"3. Prioritize must-have keywords from the JD over nice-to-have ones.\n"
            f"4. For readability fixes, identify SPECIFIC sentences and provide rewrites.\n"
            f"5. For vague statements, suggest quantified alternatives using ONLY\n"
            f"   information that could plausibly come from the user's profile.\n"
            f"Return a confidence score (0-1) for your analysis."
        )

        result = await self.ai_client.complete_json(
            prompt=prompt,
            system=self.system_prompt,
            max_tokens=3000,
            temperature=0.3,
            schema=self.output_schema,
            task_type="optimization",
        )

        # Overlay deterministic metrics (don't let LLM hallucinate these)
        if "keyword_overlap" in tool_results:
            kw = tool_results["keyword_overlap"]
            result.setdefault("keyword_analysis", {})
            result["keyword_analysis"]["match_ratio"] = kw.get("match_ratio", 0)
            result["keyword_analysis"]["exact_match_ratio"] = kw.get("exact_match_ratio", 0)
            result["keyword_analysis"]["fuzzy_matches"] = kw.get("fuzzy_matches", [])
            result["ats_score"] = round(kw.get("match_ratio", 0) * 100, 1)
        if "readability" in tool_results:
            rd = tool_results["readability"]
            result["readability_score"] = rd.get("flesch_reading_ease", 0)
            result["readability_details"] = rd
            result["readability_band"] = rd.get("quality_band", "unknown")

        return self._timed_result(
            start_ns=start,
            content=result,
            suggestions=result.get("suggestions", {}),
            metadata={
                "agent": self.name,
                "deterministic_ats_score": result.get("ats_score", 0),
                "deterministic_readability": result.get("readability_score", 0),
                "readability_band": result.get("readability_band", "unknown"),
                "missing_keywords_count": len(missing_kws),
                "improvement_plan_items": len(improvement_plan),
                "tools_used": list(tool_results.keys()),
            },
        )

    async def run_final_analysis(
        self,
        context: dict,
        *,
        initial_ats_score: float = 0.0,
        initial_readability: float = 0.0,
    ) -> AgentResult:
        """Analysis-only pass on the final revised draft.

        Scores the delivered document and produces residual recommendations
        WITHOUT mutating content. This preserves truth safety: no content
        changes happen after the final fact-check.

        Returns an AgentResult whose content is a FinalOptimizationReport.
        """
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
        else:
            draft_content = context.get("content") or context.get("draft", {})

        if isinstance(context, dict):
            jd_text = (
                context.get("jd_text", "")
                or context.get("original_context", {}).get("jd_text", "")
            )
        else:
            jd_text = ""

        draft_text = self._content_to_text(draft_content)

        # ── Deterministic tools (same as run()) ──────────────────
        tool_results: dict = {}

        kw_tool = self.tools.get("compute_keyword_overlap")
        if kw_tool and jd_text:
            try:
                tool_results["keyword_overlap"] = await kw_tool.execute(
                    document_text=draft_text, jd_text=jd_text,
                )
            except Exception as e:
                logger.warning("optimizer_final_keyword_tool_failed", error=str(e))

        read_tool = self.tools.get("compute_readability")
        if read_tool:
            try:
                tool_results["readability"] = await read_tool.execute(text=draft_text)
            except Exception as e:
                logger.warning("optimizer_final_readability_tool_failed", error=str(e))

        # ── Compute scores and deltas ─────────────────────────────
        kw_data = tool_results.get("keyword_overlap", {})
        rd_data = tool_results.get("readability", {})

        final_ats_score = round(kw_data.get("match_ratio", 0) * 100, 1)
        final_readability = rd_data.get("flesch_reading_ease", 0.0)
        missing_kws = kw_data.get("missing_from_document", [])

        keyword_gap_delta = final_ats_score - initial_ats_score
        readability_delta = final_readability - initial_readability

        # ── Build residual recommendations ────────────────────────
        residual_recommendations: list[str] = []

        if missing_kws:
            residual_recommendations.append(
                f"KEYWORD GAP: {len(missing_kws)} JD keywords still missing after revision. "
                f"Top: {', '.join(missing_kws[:5])}."
            )

        if final_readability < _IDEAL_FLESCH_MIN:
            residual_recommendations.append(
                f"READABILITY: Flesch {final_readability} still below ideal "
                f"({_IDEAL_FLESCH_MIN}-{_IDEAL_FLESCH_MAX})."
            )
        elif final_readability > _IDEAL_FLESCH_MAX:
            residual_recommendations.append(
                f"READABILITY: Flesch {final_readability} above ideal — language may be too simple."
            )

        long_sentences = rd_data.get("long_sentences", 0)
        if long_sentences > 0:
            residual_recommendations.append(
                f"SENTENCE LENGTH: {long_sentences} sentences exceed 25 words."
            )

        report = {
            "initial_ats_score": initial_ats_score,
            "final_ats_score": final_ats_score,
            "keyword_gap_delta": round(keyword_gap_delta, 1),
            "initial_readability": initial_readability,
            "final_readability": final_readability,
            "readability_delta": round(readability_delta, 1),
            "remaining_missing_keywords": missing_kws,
            "keyword_coverage": kw_data.get("match_ratio", 0),
            "residual_recommendations": residual_recommendations,
            "residual_issue_count": len(residual_recommendations),
        }

        return self._timed_result(
            start_ns=start,
            content=report,
            metadata={
                "agent": self.name,
                "stage": "optimizer_final_analysis",
                "final_ats_score": final_ats_score,
                "final_readability": final_readability,
                "residual_issue_count": len(residual_recommendations),
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

    async def run_parallel_evaluation(self, context: dict) -> dict:
        """Run ATS + Readability sub-agents in parallel for faster evaluation.

        Returns a merged dict with both ATS and readability analysis that
        can supplement the main optimizer pass.
        """
        draft_content = context.get("content") or context.get("draft", {})
        original_ctx = context.get("original_context", {}) if isinstance(context, dict) else {}

        sub_ctx = {
            "draft_content": draft_content,
            "jd_text": original_ctx.get("jd_text", ""),
        }

        agents = [
            ATSOptimizerSubAgent(ai_client=self.ai_client),
            ReadabilityOptimizerSubAgent(ai_client=self.ai_client),
        ]

        coord = SubAgentCoordinator(agents)
        results = await coord.gather(sub_ctx, timeout=45.0)

        merged: dict = {}
        for r in results:
            if r.ok:
                merged[r.agent_name] = r.data

        return merged
