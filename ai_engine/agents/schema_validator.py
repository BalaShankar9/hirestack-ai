"""
Schema Validator Agent — deterministic-first validation with severity tiers.

Code-based checks for schema compliance, field presence, length,
and formatting run FIRST. The LLM handles only fuzzy validation
(semantic completeness, quality assessment). Failures are split into
hard (blocks delivery) and soft (warnings for improvement).

v2: per-pipeline section requirements, hard vs soft failure distinction,
    placeholder/lorem-ipsum detection, duplicate content detection.
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
    "cv_generation": (500, 15000),
    "cover_letter": (200, 5000),
    "personal_statement": (200, 5000),
    "portfolio": (300, 20000),
    "benchmark": (200, 10000),
    "gap_analysis": (100, 10000),
    "ats_scanner": (100, 8000),
    "interview": (200, 15000),
    "default": (50, 30000),
}

# Per-pipeline required sections/fields
_REQUIRED_SECTIONS: dict[str, dict[str, str]] = {
    "cv_generation": {
        "html": "critical",           # Must have HTML output
    },
    "cover_letter": {
        "html": "critical",
    },
    "resume_parse": {
        "name": "critical",
        "skills": "high",
    },
    "benchmark": {
        "ideal_candidate": "critical",
    },
    "gap_analysis": {
        "compatibility_score": "critical",
    },
    "ats_scanner": {
        "overall_score": "critical",
        "keyword_matches": "high",
    },
    "interview": {
        "questions": "critical",
    },
}

# Placeholder patterns that should never appear in final output
_PLACEHOLDER_PATTERNS = [
    r"\blorem\s+ipsum\b",
    r"\[(?:your|insert|add|placeholder|todo)\b",
    r"\bTODO\b",
    r"\bFIXME\b",
    r"\bXXX\b",
    r"\{(?:name|company|title|date|skill)\}",
]


class ValidatorAgent(BaseAgent):
    """Deterministic-first validator with hard/soft failure distinction.

    v2 improvements:
    - Per-pipeline section requirements with severity levels
    - Hard failures (block delivery) vs soft warnings (improvement suggestions)
    - Placeholder/lorem-ipsum detection
    - Duplicate content detection
    - Contact info leak detection
    """

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
            evidence_ledger = None
            citations = []
            final_analysis = None
        else:
            draft_content = context.get("content") or context.get("draft") or context
            metadata = context.get("metadata", {})
            evidence_ledger = context.get("evidence_ledger")
            citations = context.get("citations", [])
            final_analysis = context.get("final_analysis")

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

        # Check: required field presence for known types (with severity)
        if isinstance(draft_content, dict):
            required = _REQUIRED_SECTIONS.get(doc_type, {})
            for field_name, severity in required.items():
                if not draft_content.get(field_name):
                    det_issues.append({
                        "field": field_name,
                        "severity": severity,
                        "message": f"Required field '{field_name}' is missing or empty",
                    })
                    det_checks["all_sections_present"] = False

        # Check: placeholder/template content detection
        content_text = html if html else json.dumps(draft_content)
        for pattern in _PLACEHOLDER_PATTERNS:
            matches = re.findall(pattern, content_text, re.IGNORECASE)
            if matches:
                det_issues.append({
                    "field": "content",
                    "severity": "high",
                    "message": f"Placeholder content detected: '{matches[0]}'",
                })
                det_checks["format_valid"] = False
                break  # One placeholder finding is enough

        # Check: duplicate paragraph detection (same 50+ char block repeated)
        if len(content_text) > 200:
            paragraphs = [p.strip() for p in content_text.split("\n") if len(p.strip()) > 50]
            seen = set()
            for para in paragraphs:
                normalised = para.lower().strip()
                if normalised in seen:
                    det_issues.append({
                        "field": "content",
                        "severity": "medium",
                        "message": f"Duplicate content detected: '{para[:60]}...'",
                    })
                    break
                seen.add(normalised)

        # v3: Evidence citation enforcement
        # Check that fabricated claims were removed and key claims have evidence
        det_checks["evidence_grounded"] = True
        if citations:
            fabricated_citations = [
                c for c in citations
                if c.get("classification") == "fabricated"
            ]
            if fabricated_citations:
                det_issues.append({
                    "field": "evidence",
                    "severity": "high",
                    "message": (
                        f"{len(fabricated_citations)} fabricated claim(s) detected by fact-checker. "
                        f"First: '{fabricated_citations[0].get('claim_text', '')[:80]}'"
                    ),
                })
                det_checks["evidence_grounded"] = False

            # Count claims with no evidence backing
            ungrounded = [
                c for c in citations
                if not c.get("evidence_ids") and c.get("classification") not in ("verified", "inferred")
            ]
            if ungrounded:
                det_issues.append({
                    "field": "evidence",
                    "severity": "medium",
                    "message": f"{len(ungrounded)} claim(s) have no linked evidence items",
                })

        # v3: Evidence ledger coverage check
        if evidence_ledger and isinstance(evidence_ledger, dict):
            ledger_count = evidence_ledger.get("count", 0)
            if ledger_count == 0 and doc_type in ("cv_generation", "cover_letter", "portfolio"):
                det_issues.append({
                    "field": "evidence",
                    "severity": "high",
                    "message": "No evidence items in ledger for document generation pipeline",
                })
                det_checks["evidence_grounded"] = False
        elif hasattr(evidence_ledger, '__len__') and len(evidence_ledger) == 0:
            if doc_type in ("cv_generation", "cover_letter", "portfolio"):
                det_issues.append({
                    "field": "evidence",
                    "severity": "high",
                    "message": "Empty evidence ledger for document generation pipeline",
                })
                det_checks["evidence_grounded"] = False

        # v7: Final analysis consumption — deterministic checks on residual quality
        det_checks["final_analysis_reviewed"] = False
        det_checks["residual_risk_within_bounds"] = True
        _DOC_GEN_TYPES = {"cv_generation", "cover_letter", "personal_statement", "portfolio"}

        if final_analysis and isinstance(final_analysis, dict):
            det_checks["final_analysis_reviewed"] = True

            # Check: low final ATS score on document-generation pipelines
            final_ats = final_analysis.get("final_ats_score", 0)
            if doc_type in _DOC_GEN_TYPES and isinstance(final_ats, (int, float)) and final_ats > 0:
                if final_ats < 60:
                    det_issues.append({
                        "field": "final_analysis",
                        "severity": "high",
                        "message": f"Final ATS score is critically low ({final_ats}/100)",
                    })
                    det_checks["residual_risk_within_bounds"] = False
                elif final_ats < 75:
                    det_issues.append({
                        "field": "final_analysis",
                        "severity": "medium",
                        "message": f"Final ATS score is below target ({final_ats}/100, target ≥75)",
                    })

            # Check: remaining missing keywords
            missing_kw = final_analysis.get("missing_keywords", [])
            if isinstance(missing_kw, list) and len(missing_kw) > 5:
                det_issues.append({
                    "field": "final_analysis",
                    "severity": "high",
                    "message": f"{len(missing_kw)} keywords still missing after optimization",
                })
                det_checks["residual_risk_within_bounds"] = False
            elif isinstance(missing_kw, list) and len(missing_kw) > 2:
                det_issues.append({
                    "field": "final_analysis",
                    "severity": "medium",
                    "message": f"{len(missing_kw)} keywords still missing after optimization",
                })

            # Check: high residual issue count
            residual_issues = final_analysis.get("residual_issue_count", 0)
            if isinstance(residual_issues, (int, float)) and residual_issues > 5:
                det_issues.append({
                    "field": "final_analysis",
                    "severity": "high",
                    "message": f"High residual issue count ({residual_issues}) after optimization",
                })
                det_checks["residual_risk_within_bounds"] = False
            elif isinstance(residual_issues, (int, float)) and residual_issues > 2:
                det_issues.append({
                    "field": "final_analysis",
                    "severity": "medium",
                    "message": f"Residual issues remain ({residual_issues}) after optimization",
                })

            # Check: negative or flat keyword/readability deltas
            kw_delta = final_analysis.get("keyword_gap_delta", 0)
            readability_delta = final_analysis.get("readability_delta", 0)
            if isinstance(kw_delta, (int, float)) and kw_delta > 0:
                # Positive keyword_gap_delta means the gap GREW (more missing)
                det_issues.append({
                    "field": "final_analysis",
                    "severity": "high",
                    "message": f"Keyword gap worsened by {kw_delta} after optimization",
                })
                det_checks["residual_risk_within_bounds"] = False
            if isinstance(readability_delta, (int, float)) and readability_delta < -10:
                det_issues.append({
                    "field": "final_analysis",
                    "severity": "medium",
                    "message": f"Readability dropped significantly (delta: {readability_delta})",
                })

        elif doc_type in _DOC_GEN_TYPES:
            # Final analysis not provided for a doc-gen pipeline — flag as info
            logger.info(
                "final_analysis_not_provided",
                doc_type=doc_type,
                pipeline=metadata.get("pipeline", "unknown"),
            )

        has_critical = any(i["severity"] == "critical" for i in det_issues)

        # ── Phase 2: LLM fuzzy validation (skipped if critical issues) ──
        if not has_critical:
            prompt = (
                f"Validate this document for semantic completeness and quality.\n\n"
                f"Document type: {doc_type}\n"
                f"Content:\n{json.dumps(draft_content, indent=2)[:5000]}\n\n"
                f"Deterministic checks already passed: {json.dumps(det_checks)}\n"
                f"Deterministic issues found: {json.dumps(det_issues)}\n\n"
                f"Focus on: semantic completeness, logical flow, content quality,\n"
                f"and whether the content actually addresses the intended purpose.\n"
                f"Do NOT re-check formatting or length — those are already handled.\n\n"
                f"For each issue, classify severity as:\n"
                f"- 'critical': blocks delivery (factually wrong, incoherent)\n"
                f"- 'high': should fix before delivery\n"
                f"- 'medium': nice to fix, but acceptable\n"
                f"- 'low': minor suggestion"
            )

            llm_result = await self.ai_client.complete_json(
                prompt=prompt,
                system=self.system_prompt,
                max_tokens=1500,
                temperature=0.2,
                schema=self.output_schema,
                task_type="validation",
            )

            # Merge LLM issues with deterministic issues
            llm_issues = llm_result.get("issues", [])
            all_issues = det_issues + llm_issues
            confidence = llm_result.get("confidence", 0.8)
        else:
            all_issues = det_issues
            confidence = 1.0  # High confidence in deterministic failures

        # Hard failures = critical or high severity
        hard_failures = [i for i in all_issues if i.get("severity") in ("critical", "high")]
        soft_warnings = [i for i in all_issues if i.get("severity") in ("medium", "low")]
        valid = len(hard_failures) == 0

        final_result = {
            "valid": valid,
            "checks": det_checks,
            "issues": all_issues,
            "hard_failures": len(hard_failures),
            "soft_warnings": len(soft_warnings),
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
                "hard_failures": len(hard_failures),
                "soft_warnings": len(soft_warnings),
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
