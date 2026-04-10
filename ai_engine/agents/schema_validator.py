"""
Schema Validator Agent — deterministic-first validation.

Code-based checks for schema compliance, field presence, length,
and formatting run FIRST. The LLM handles only fuzzy validation
(semantic completeness, quality assessment).
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

import structlog

from ai_engine.agents.base import BaseAgent, AgentResult
from ai_engine.agents.schemas import VALIDATOR_SCHEMA
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.agents.validator")

_PROMPT_PATH = Path(__file__).parent / "prompts" / "schema_validator_system.md"

# Length thresholds by document type (characters)
_LENGTH_BOUNDS: dict[str, tuple[int, int]] = {
    "cv": (500, 15000),
    "cover_letter": (200, 5000),
    "personal_statement": (200, 5000),
    "portfolio": (300, 20000),
    "default": (50, 30000),
}


class ValidatorAgent(BaseAgent):
    """Deterministic-first validator — code checks, then LLM for fuzzy validation."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        system_prompt = _PROMPT_PATH.read_text() if _PROMPT_PATH.exists() else ""
        super().__init__(
            name="validator",
            system_prompt=system_prompt,
            output_schema=VALIDATOR_SCHEMA,
            ai_client=ai_client,
        )

    async def run(self, context: dict) -> AgentResult:
        start = time.monotonic_ns()

        if isinstance(context, AgentResult):
            draft_content = context.content
            metadata = {}
        else:
            draft_content = context.get("content") or context.get("draft") or context
            metadata = context.get("metadata", {})

        doc_type = metadata.get("pipeline", metadata.get("agent", "default"))

        # ── Phase 1: Deterministic checks ─────────────────────────
        det_issues: list[dict] = []
        det_checks = {
            "schema_compliant": True,
            "format_valid": True,
            "all_sections_present": True,
            "length_appropriate": True,
        }

        # Check: non-empty content
        if not draft_content or (isinstance(draft_content, dict) and not any(
            v for v in draft_content.values() if v
        )):
            det_issues.append({
                "field": "content",
                "severity": "critical",
                "message": "Content is empty or all fields are empty",
            })
            det_checks["schema_compliant"] = False

        # Check: HTML validity (if html field exists)
        html = draft_content.get("html", "") if isinstance(draft_content, dict) else ""
        if html:
            unclosed = self._check_html_tags(html)
            if unclosed:
                det_issues.append({
                    "field": "html",
                    "severity": "high",
                    "message": f"Unclosed HTML tags: {', '.join(unclosed[:5])}",
                })
                det_checks["format_valid"] = False

        # Check: length bounds
        content_len = len(html) if html else len(json.dumps(draft_content))
        min_len, max_len = _LENGTH_BOUNDS.get(doc_type, _LENGTH_BOUNDS["default"])
        if content_len < min_len:
            det_issues.append({
                "field": "length",
                "severity": "high",
                "message": f"Content too short ({content_len} chars, min {min_len})",
            })
            det_checks["length_appropriate"] = False
        elif content_len > max_len:
            det_issues.append({
                "field": "length",
                "severity": "medium",
                "message": f"Content too long ({content_len} chars, max {max_len})",
            })
            det_checks["length_appropriate"] = False

        # Check: required field presence for known types
        if isinstance(draft_content, dict):
            required_fields = self._required_fields_for(doc_type)
            for field in required_fields:
                if not draft_content.get(field):
                    det_issues.append({
                        "field": field,
                        "severity": "medium",
                        "message": f"Required field '{field}' is missing or empty",
                    })
                    det_checks["all_sections_present"] = False

        has_critical = any(i["severity"] == "critical" for i in det_issues)

        # ── Phase 2: LLM fuzzy validation (skipped if critical issues) ──
        if not has_critical:
            prompt = (
                f"Validate this document for semantic completeness and quality.\n\n"
                f"Content:\n{json.dumps(draft_content, indent=2)[:5000]}\n\n"
                f"Deterministic checks already passed: {json.dumps(det_checks)}\n"
                f"Deterministic issues found: {json.dumps(det_issues)}\n\n"
                f"Focus on: semantic completeness, logical flow, and content quality.\n"
                f"Do NOT re-check formatting or length — those are already handled."
            )

            llm_result = await self.ai_client.complete_json(
                prompt=prompt,
                system=self.system_prompt,
                max_tokens=1500,
                temperature=0.2,
                schema=self.output_schema,
            )

            # Merge LLM issues with deterministic issues
            llm_issues = llm_result.get("issues", [])
            all_issues = det_issues + llm_issues
            confidence = llm_result.get("confidence", 0.8)
        else:
            all_issues = det_issues
            confidence = 1.0  # High confidence in deterministic failures

        valid = len([i for i in all_issues if i.get("severity") in ("critical", "high")]) == 0

        final_result = {
            "valid": valid,
            "checks": det_checks,
            "issues": all_issues,
            "confidence": confidence,
            "content": draft_content,
        }

        return self._timed_result(
            start_ns=start,
            content=final_result,
            flags=[f"validation_issue: {i['message']}" for i in all_issues],
            metadata={
                "agent": self.name,
                "valid": valid,
                "deterministic_issues": len(det_issues),
                "total_issues": len(all_issues),
            },
        )

    @staticmethod
    def _check_html_tags(html: str) -> list[str]:
        """Return list of unclosed HTML tags."""
        # Simple stack-based check for common tags
        open_tags: list[str] = []
        void_elements = {
            "br", "hr", "img", "input", "meta", "link", "area",
            "base", "col", "embed", "source", "track", "wbr",
        }
        for match in re.finditer(r"<(/?)(\w+)[^>]*>", html):
            is_close = match.group(1) == "/"
            tag = match.group(2).lower()
            if tag in void_elements:
                continue
            if is_close:
                if open_tags and open_tags[-1] == tag:
                    open_tags.pop()
            else:
                open_tags.append(tag)
        return open_tags

    @staticmethod
    def _required_fields_for(doc_type: str) -> list[str]:
        """Return required fields for a document type."""
        mapping: dict[str, list[str]] = {
            "cv_generation": ["html"],
            "cover_letter": ["html"],
            "resume_parse": ["name", "skills"],
            "benchmark": ["ideal_candidate"],
            "gap_analysis": ["compatibility_score"],
            "ats_scanner": ["overall_score", "keyword_matches"],
            "interview": ["questions"],
        }
        return mapping.get(doc_type, [])
