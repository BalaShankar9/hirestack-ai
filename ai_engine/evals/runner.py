"""
Evaluation Runner — runs gold corpus through deterministic tools and
evaluates outputs against expected properties.

Usage:
    python -m ai_engine.evals.runner            # Run all evals
    python -m ai_engine.evals.runner --case 0   # Run single case by index
    python -m ai_engine.evals.runner --verbose   # Detailed output

This runner exercises the DETERMINISTIC components only (tools, claim
extraction, matching) so it can run without API keys or LLM access.
For full pipeline evaluation, use the pipeline eval harness with live APIs.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from ai_engine.agents.tools import (
    _parse_jd,
    _extract_profile_evidence,
    _compute_keyword_overlap,
    _compute_readability,
    _extract_claims,
    _match_claims_to_evidence,
)
from ai_engine.agents.evidence import (
    EvidenceLedger,
    populate_from_profile,
    populate_from_jd,
    populate_from_tool_result,
)
from ai_engine.evals.gold_corpus import GOLD_CASES, GoldCase


@dataclass
class ToolEvalResult:
    """Result of evaluating a single gold case through the tool suite."""
    case_name: str
    pipeline: str
    passed: bool = True
    scores: dict[str, float] = field(default_factory=dict)
    failures: list[str] = field(default_factory=list)
    duration_ms: int = 0

    def to_dict(self) -> dict:
        return {
            "case": self.case_name,
            "pipeline": self.pipeline,
            "passed": self.passed,
            "scores": self.scores,
            "failures": self.failures,
            "duration_ms": self.duration_ms,
        }


@dataclass
class EvalRunReport:
    """Aggregate report from running all eval cases."""
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    results: list[ToolEvalResult] = field(default_factory=list)
    total_duration_ms: int = 0
    aggregate_scores: dict[str, float] = field(default_factory=dict)

    def add(self, result: ToolEvalResult) -> None:
        self.results.append(result)
        self.total_cases += 1
        if result.passed:
            self.passed_cases += 1
        else:
            self.failed_cases += 1
        self.total_duration_ms += result.duration_ms
        for k, v in result.scores.items():
            if k not in self.aggregate_scores:
                self.aggregate_scores[k] = 0.0
            self.aggregate_scores[k] += v

    def finalise(self) -> None:
        if self.total_cases > 0:
            for k in self.aggregate_scores:
                self.aggregate_scores[k] = round(
                    self.aggregate_scores[k] / self.total_cases, 3,
                )

    def to_dict(self) -> dict:
        return {
            "total_cases": self.total_cases,
            "passed": self.passed_cases,
            "failed": self.failed_cases,
            "pass_rate": round(self.passed_cases / max(self.total_cases, 1), 3),
            "total_duration_ms": self.total_duration_ms,
            "aggregate_scores": self.aggregate_scores,
            "results": [r.to_dict() for r in self.results],
        }


async def evaluate_case(case: GoldCase, verbose: bool = False) -> ToolEvalResult:
    """Run a single gold case through the deterministic tool suite."""
    start = time.monotonic_ns()
    result = ToolEvalResult(case_name=case.name, pipeline=case.pipeline)

    ctx = case.context
    jd_text = ctx.get("jd_text", "")
    user_profile = ctx.get("user_profile", {})

    # Run all deterministic tools
    jd_result = await _parse_jd(jd_text=jd_text) if jd_text else {}
    evidence = await _extract_profile_evidence(user_profile=user_profile) if user_profile else {}

    # Create a synthetic document text from profile for overlap
    profile_text_parts = evidence.get("skills", []) + evidence.get("titles", [])
    profile_text = " ".join(str(p) for p in profile_text_parts)

    overlap = {}
    if jd_text and profile_text:
        overlap = await _compute_keyword_overlap(
            document_text=profile_text, jd_text=jd_text,
        )

    readability = await _compute_readability(text=jd_text) if jd_text else {}

    # Build a mock draft text from profile for claim extraction
    draft_parts = []
    for exp in user_profile.get("experience", []):
        if isinstance(exp, dict):
            desc = exp.get("description", "")
            title = exp.get("title", "")
            company = exp.get("company", "")
            if desc:
                draft_parts.append(desc)
            if title and company:
                draft_parts.append(f"Worked as {title} at {company}")
    draft_text = ". ".join(draft_parts) if draft_parts else "No draft available"

    claims_result = await _extract_claims(document_text=draft_text)
    claims = claims_result.get("claims", [])

    match_result = {}
    if claims and evidence:
        match_result = await _match_claims_to_evidence(
            claims=claims, evidence=evidence,
        )

    # ── Score against expected properties ──────────────────────
    combined_output = {
        "jd_parsed": jd_result,
        "evidence": evidence,
        "keyword_overlap": overlap,
        "readability": readability,
        "claims": claims_result,
        "claim_matching": match_result,
    }

    # v3: Build evidence ledger from tool results and score it
    ledger = EvidenceLedger()
    if user_profile:
        populate_from_profile(ledger, user_profile)
    if jd_result:
        populate_from_jd(ledger, jd_result)
    if overlap:
        populate_from_tool_result(ledger, "compute_keyword_overlap", overlap)
    if evidence:
        populate_from_tool_result(ledger, "extract_profile_evidence", evidence)
    combined_output["evidence_ledger"] = ledger

    for prop_name, assertion_fn in case.expected_properties.items():
        try:
            passed = assertion_fn(combined_output)
            if not passed:
                result.failures.append(f"Property '{prop_name}' assertion failed")
                result.passed = False
        except Exception as e:
            result.failures.append(f"Property '{prop_name}' raised: {e}")
            result.passed = False

    # Check failure conditions (things that should NOT happen)
    for condition_name, condition_fn in case.failure_conditions.items():
        try:
            triggered = condition_fn(combined_output)
            if triggered:
                result.failures.append(f"Failure condition '{condition_name}' triggered")
                result.passed = False
        except Exception as e:
            result.failures.append(f"Failure condition '{condition_name}' raised: {e}")

    # Compute scores
    if jd_result:
        result.scores["jd_keyword_count"] = min(1.0, len(jd_result.get("top_keywords", [])) / 10)
    if evidence:
        result.scores["evidence_completeness"] = min(1.0, (
            len(evidence.get("skills", []))
            + len(evidence.get("companies", []))
            + len(evidence.get("titles", []))
        ) / 10)
    if overlap:
        result.scores["keyword_match_ratio"] = overlap.get("match_ratio", 0)
    if match_result:
        result.scores["claim_match_rate"] = match_result.get("match_rate", 0)
    if claims:
        result.scores["claims_extracted"] = min(1.0, len(claims) / 5)

    # v3: Evidence ledger metrics
    if len(ledger) > 0:
        result.scores["evidence_items_total"] = min(1.0, len(ledger) / 20)
        tier_counts = ledger.to_dict()["tier_counts"]
        verbatim = tier_counts.get("verbatim", 0)
        total = len(ledger)
        result.scores["evidence_verbatim_ratio"] = round(verbatim / max(total, 1), 3)
        source_counts = ledger.to_dict()["source_counts"]
        sources_used = sum(1 for v in source_counts.values() if v > 0)
        result.scores["evidence_source_diversity"] = round(sources_used / 5, 3)

    # Apply scoring rules from gold case
    for rule_name, rule_fn in case.scoring_rules.items():
        try:
            score = rule_fn(combined_output)
            result.scores[rule_name] = round(score, 3)
        except Exception:
            result.scores[rule_name] = 0.0

    elapsed = (time.monotonic_ns() - start) // 1_000_000
    result.duration_ms = elapsed

    if verbose:
        status = "PASS" if result.passed else "FAIL"
        print(f"  [{status}] {case.name} ({elapsed}ms)")
        if result.failures:
            for f in result.failures:
                print(f"    - {f}")

    return result


async def run_all(
    cases: list[GoldCase] | None = None,
    verbose: bool = False,
) -> EvalRunReport:
    """Run all gold cases and produce an aggregate report."""
    cases = cases or GOLD_CASES
    report = EvalRunReport()

    if verbose:
        print(f"\nRunning {len(cases)} evaluation cases...\n")

    for case in cases:
        result = await evaluate_case(case, verbose=verbose)
        report.add(result)

    report.finalise()

    if verbose:
        print(f"\n{'='*50}")
        print(f"Results: {report.passed_cases}/{report.total_cases} passed")
        print(f"Duration: {report.total_duration_ms}ms")
        print(f"Aggregate scores: {json.dumps(report.aggregate_scores, indent=2)}")

    return report


def main() -> None:
    """CLI entry point."""
    import argparse
    parser = argparse.ArgumentParser(description="Run agent evaluation suite")
    parser.add_argument("--case", type=int, help="Run single case by index")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    if args.case is not None:
        if 0 <= args.case < len(GOLD_CASES):
            cases = [GOLD_CASES[args.case]]
        else:
            print(f"Invalid case index {args.case}. Valid: 0-{len(GOLD_CASES)-1}")
            sys.exit(1)
    else:
        cases = GOLD_CASES

    report = asyncio.run(run_all(cases, verbose=args.verbose or True))

    if report.failed_cases > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
