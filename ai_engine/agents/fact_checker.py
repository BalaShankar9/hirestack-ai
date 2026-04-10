"""
Fact-Checker Agent — evidence-bound verification with tool loop.

Extracts claims, maps each to source evidence, and classifies
unsupported claims. Uses deterministic tools first, then LLM for
nuanced classification of ambiguous claims.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import structlog

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import FACT_CHECKER_SCHEMA
from ai_engine.agents.tools import ToolRegistry, build_fact_checker_tools
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.agents.fact_checker")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "fact_checker_system.md"


class FactCheckerAgent(BaseAgent):
    """Evidence-bound fact checker — deterministic claim extraction + LLM classification."""

    MAX_TOOL_STEPS = 4

    def __init__(
        self,
        ai_client: Optional[AIClient] = None,
        tools: Optional[ToolRegistry] = None,
    ):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="fact_checker",
            system_prompt=system_prompt,
            output_schema=FACT_CHECKER_SCHEMA,
            ai_client=ai_client,
        )
        self.tools = tools or build_fact_checker_tools()

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        # Extract inputs from context (handles both dict and AgentResult)
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

        # Flatten draft content to text for tool processing
        draft_text = self._content_to_text(draft_content)

        # ── Deterministic tool phase ──────────────────────────────
        # Step 1: Extract evidence from profile
        evidence_tool = self.tools.get("extract_profile_evidence")
        evidence: dict = {}
        if evidence_tool:
            try:
                evidence = await evidence_tool.execute(user_profile=user_profile)
            except Exception as e:
                logger.warning("fact_check_evidence_failed", error=str(e))

        # Step 2: Extract claims from document
        claims_tool = self.tools.get("extract_claims")
        extracted_claims: list[dict] = []
        if claims_tool:
            try:
                claims_result = await claims_tool.execute(document_text=draft_text)
                extracted_claims = claims_result.get("claims", [])
            except Exception as e:
                logger.warning("fact_check_claims_failed", error=str(e))

        # Step 3: Deterministic claim-evidence matching
        match_tool = self.tools.get("match_claims_to_evidence")
        match_result: dict = {}
        if match_tool and extracted_claims:
            try:
                match_result = await match_tool.execute(
                    claims=extracted_claims, evidence=evidence,
                )
            except Exception as e:
                logger.warning("fact_check_match_failed", error=str(e))

        # ── LLM classification phase ─────────────────────────────
        # The LLM classifies unmatched claims and refines matched ones.
        # Deterministic matching gives it a head start.
        unmatched = match_result.get("unmatched_claims", [])
        matched = match_result.get("matched_claims", [])

        classification_prompt = (
            f"Verify every claim in this document against the user's profile data.\n\n"
            f"## Draft Content\n{json.dumps(draft_content, indent=2)[:4000]}\n\n"
            f"## Source Profile Evidence\n{json.dumps(evidence, indent=2)[:2000]}\n\n"
            f"## Pre-matched Claims (deterministic)\n"
            f"These claims had keyword matches to profile evidence:\n"
            f"{json.dumps(matched[:20], indent=2)[:2000]}\n\n"
            f"## Unmatched Claims (need your judgment)\n"
            f"These claims had NO keyword match — classify as verified/enhanced/fabricated:\n"
            f"{json.dumps(unmatched[:20], indent=2)[:2000]}\n\n"
            f"Classify ALL claims. Pre-matched claims are likely verified or enhanced.\n"
            f"Unmatched claims need careful judgment — they may be enhanced (valid reframing)\n"
            f"or fabricated (no basis in profile at all).\n"
            f"Return a confidence score (0-1) for your overall assessment."
        )

        result = await self.ai_client.complete_json(
            prompt=classification_prompt,
            system=self.system_prompt,
            max_tokens=4000,
            temperature=0.2,
            schema=self.output_schema,
        )

        result["deterministic_match_rate"] = match_result.get("match_rate", 0)
        result["total_claims_extracted"] = len(extracted_claims)
        result["tools_used"] = [
            "extract_profile_evidence",
            "extract_claims",
            "match_claims_to_evidence",
        ]

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
                "deterministic_match_rate": match_result.get("match_rate", 0),
                "total_claims_extracted": len(extracted_claims),
                "tools_used": result["tools_used"],
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
                    elif isinstance(item, dict):
                        parts.append(json.dumps(item))
        return "\n".join(parts) if parts else json.dumps(content)
