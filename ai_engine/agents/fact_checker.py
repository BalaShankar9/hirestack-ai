"""
Fact-Checker Agent — evidence-bound verification with claim-level tracing.

Extracts claims, maps each to source evidence spans, and classifies
using a 4-tier taxonomy: verified → inferred → embellished → fabricated.
Deterministic tools provide the evidence map; the LLM adjudicates only
the ambiguous claims where deterministic matching is inconclusive.

v2: 4-tier classification, per-claim evidence spans, deterministic
    pre-classification to minimise LLM hallucinated approvals/rejections,
    fabrication recall ≥ 0.90 target.
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

# Deterministic confidence thresholds for pre-classification
_HIGH_CONF = 0.80   # ≥ this → auto-classify as verified (skip LLM)
_MED_CONF = 0.40    # ≥ this → present to LLM as "likely verified/inferred"
                     # < this → present to LLM as "needs judgment"


class FactCheckerAgent(BaseAgent):
    """Evidence-bound fact checker with 4-tier classification and claim-level tracing.

    Classification tiers:
      verified   – claim directly maps to profile data (exact evidence span)
      inferred   – claim is reasonable extrapolation from evidence (e.g. seniority from tenure)
      embellished – strategic reframing of real experience (allowed, flagged for awareness)
      fabricated – NO basis in any profile data (must be removed)
    """

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

        # ── Deterministic pre-classification ──────────────────────
        # High-confidence matches are auto-classified without LLM
        auto_verified: list[dict] = []
        needs_llm: list[dict] = []

        for claim in match_result.get("matched_claims", []):
            conf = claim.get("match_confidence", 0)
            sources = claim.get("sources", [])
            if conf >= _HIGH_CONF:
                auto_verified.append({
                    "text": claim.get("text", ""),
                    "classification": "verified",
                    "source_reference": ", ".join(sources),
                    "evidence_sources": sources,  # structured list for deterministic binding
                    "confidence": round(conf, 2),
                    "method": "deterministic",
                })
            else:
                # Carry sources through so orchestrator can attempt binding
                claim["evidence_sources"] = sources
                needs_llm.append(claim)

        # All unmatched claims need LLM adjudication
        unmatched = match_result.get("unmatched_claims", [])
        needs_llm.extend(unmatched)

        # ── LLM classification phase ─────────────────────────────
        # Only send ambiguous claims to the LLM — saves tokens and
        # prevents the LLM from overriding correct deterministic matches.
        llm_classified: list[dict] = []
        if needs_llm:
            classification_prompt = (
                f"Classify each claim below using EXACTLY one of these tiers:\n"
                f"- **verified**: directly maps to profile data\n"
                f"- **inferred**: reasonable extrapolation from evidence\n"
                f"- **embellished**: strategic reframing of real experience (allowed but flagged)\n"
                f"- **fabricated**: NO basis in any profile data (must remove)\n\n"
                f"## Source Profile Evidence\n{json.dumps(evidence, indent=2)[:2000]}\n\n"
                f"## Claims Needing Classification ({len(needs_llm)} claims)\n"
                f"Each claim below had weak or no deterministic match to evidence.\n"
                f"For each, provide the classification, the specific evidence span it maps to\n"
                f"(or 'none' if fabricated), and your confidence (0-1).\n\n"
                f"{json.dumps(needs_llm[:25], indent=2)[:3000]}\n\n"
                f"## Already Verified ({len(auto_verified)} claims auto-verified)\n"
                f"These had strong deterministic evidence matches — do NOT reclassify them.\n\n"
                f"IMPORTANT: Err on the side of 'embellished' over 'fabricated' when\n"
                f"the claim could reasonably derive from ANY profile data. Only classify\n"
                f"as 'fabricated' when there is truly ZERO basis in the profile.\n"
                f"Return a confidence score (0-1) for your overall assessment."
            )

            result = await self.ai_client.complete_json(
                prompt=classification_prompt,
                system=self.system_prompt,
                max_tokens=4000,
                temperature=0.2,
                schema=self.output_schema,
                task_type="fact_checking",
            )
            llm_classified = result.get("claims", [])
        else:
            result = {}

        # ── Merge deterministic + LLM classifications ─────────────
        all_claims = auto_verified + llm_classified

        # Normalise classification values (LLM might use old taxonomy)
        _CLASSIFICATION_MAP = {
            "enhanced": "embellished",  # Map old taxonomy → new
            "supported": "verified",
            "unsupported": "fabricated",
        }
        for claim in all_claims:
            raw = claim.get("classification", "").lower().strip()
            claim["classification"] = _CLASSIFICATION_MAP.get(raw, raw)

        # Build summary counts
        summary = {"verified": 0, "inferred": 0, "embellished": 0, "fabricated": 0}
        fabricated_claims: list[dict] = []
        for claim in all_claims:
            cls = claim.get("classification", "")
            if cls in summary:
                summary[cls] += 1
            if cls == "fabricated":
                fabricated_claims.append(claim)

        # For backward compat, map to old schema field "enhanced"
        summary["enhanced"] = summary.get("inferred", 0) + summary.get("embellished", 0)

        total_classified = sum(summary[k] for k in ("verified", "inferred", "embellished", "fabricated"))
        overall_accuracy = (
            (summary["verified"] + summary["inferred"]) / max(total_classified, 1)
        )

        final_result = {
            "claims": all_claims,
            "summary": summary,
            "fabricated_claims": fabricated_claims,
            "overall_accuracy": round(overall_accuracy, 3),
            "confidence": result.get("confidence", 0.9 if not needs_llm else 0.5),
            "deterministic_match_rate": match_result.get("match_rate", 0),
            "total_claims_extracted": len(extracted_claims),
            "auto_verified_count": len(auto_verified),
            "llm_classified_count": len(llm_classified),
            "tools_used": [
                "extract_profile_evidence",
                "extract_claims",
                "match_claims_to_evidence",
            ],
        }

        # Categorize fabricated/embellished claims for targeted re-research
        claim_categories = self._categorize_claims(fabricated_claims + [
            c for c in all_claims if c.get("classification") == "embellished"
        ])
        final_result["claim_categories"] = claim_categories

        flags = [f"fabricated: {c.get('text', '')}" for c in fabricated_claims]

        return self._timed_result(
            start_ns=start,
            content=final_result,
            flags=flags,
            metadata={
                "agent": self.name,
                "verified": summary.get("verified", 0),
                "inferred": summary.get("inferred", 0),
                "embellished": summary.get("embellished", 0),
                "fabricated": summary.get("fabricated", 0),
                "deterministic_match_rate": match_result.get("match_rate", 0),
                "total_claims_extracted": len(extracted_claims),
                "auto_verified_count": len(auto_verified),
                "tools_used": final_result["tools_used"],
            },
        )

    @staticmethod
    def _categorize_claims(claims: list[dict]) -> list[str]:
        """Categorize problem claims into actionable categories for targeted re-research.

        Categories: companies, dates, metrics, technologies, certifications, roles
        """
        import re as _re

        categories: set[str] = set()
        for claim in claims:
            text = (claim.get("text", "") or "").lower()
            if not text:
                continue
            # Companies — proper nouns, "at X", "for X"
            if _re.search(r'\b(?:at|for|with|joined)\s+[A-Z]', claim.get("text", "")):
                categories.add("companies")
            # Dates / years
            if _re.search(r'\b(?:19|20)\d{2}\b', text) or _re.search(r'\b\d+\s*(?:year|month)', text):
                categories.add("dates")
            # Metrics — numbers with units ($, %, K, M)
            if _re.search(r'[\$€£]\s*\d|(?:\d+(?:\.\d+)?)\s*[%KMBkmb]|\d{2,}', text):
                categories.add("metrics")
            # Technologies / tools
            tech_patterns = (
                r'\b(?:python|java|react|aws|azure|gcp|docker|kubernetes|sql|'
                r'tensorflow|pytorch|node|typescript|javascript|c\+\+|go|rust)\b'
            )
            if _re.search(tech_patterns, text):
                categories.add("technologies")
            # Certifications
            if _re.search(r'\b(?:certified|certification|certificate|pmp|aws certified|cpa|cfa)\b', text):
                categories.add("certifications")
            # Roles / titles
            if _re.search(r'\b(?:manager|director|lead|senior|principal|vp|head of|chief)\b', text):
                categories.add("roles")

        return sorted(categories)

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
