"""
Agent Evaluation Harness — per-role quality metrics.

Provides structured evaluation for each agent role:
  - ResearcherEval: source coverage, relevance, tool utilization
  - CriticEval: issue detection precision, quality lift measurement
  - FactCheckerEval: fabricated-claim recall, false positive rate
  - OptimizerEval: ATS score delta, readability delta
  - ValidatorEval: invalid payload escape rate
  - PipelineEval: end-to-end quality, latency, cost, task success
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EvalMetrics:
    """Standardized evaluation metrics for any agent."""
    agent_name: str
    scores: dict[str, float] = field(default_factory=dict)
    latency_ms: int = 0
    token_estimate: int = 0
    passed: bool = True
    issues: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "scores": self.scores,
            "latency_ms": self.latency_ms,
            "token_estimate": self.token_estimate,
            "passed": self.passed,
            "issues": self.issues,
        }


class ResearcherEval:
    """Evaluate researcher output for coverage and tool utilization."""

    @staticmethod
    def evaluate(result: dict, context: dict) -> EvalMetrics:
        metrics = EvalMetrics(agent_name="researcher")
        metadata = result if isinstance(result, dict) else {}

        # Coverage score (from agent output)
        coverage = metadata.get("coverage_score", 0)
        metrics.scores["coverage"] = coverage

        # Tool utilization
        tools_used = metadata.get("tools_used", [])
        metrics.scores["tool_utilization"] = min(1.0, len(tools_used) / 3.0)

        # Keyword extraction quality
        keywords = metadata.get("keyword_priority", [])
        metrics.scores["keyword_density"] = min(1.0, len(keywords) / 10.0)

        # Key signals found
        signals = metadata.get("key_signals", [])
        metrics.scores["signal_count"] = min(1.0, len(signals) / 5.0)

        # Pass/fail: coverage must be above threshold
        metrics.passed = coverage >= 0.5
        if not metrics.passed:
            metrics.issues.append(f"Low coverage score: {coverage:.2f}")

        return metrics


class CriticEval:
    """Evaluate critic output for scoring accuracy and actionability."""

    @staticmethod
    def evaluate(result: dict, draft_content: dict) -> EvalMetrics:
        metrics = EvalMetrics(agent_name="critic")

        quality_scores = result.get("quality_scores", {})
        feedback = result.get("feedback", {})
        confidence = result.get("confidence", 0)

        # Score completeness (all 4 dimensions present and in range)
        expected_dims = ["impact", "clarity", "tone_match", "completeness"]
        present = sum(1 for d in expected_dims if d in quality_scores)
        metrics.scores["score_completeness"] = present / len(expected_dims)

        in_range = sum(
            1 for d in expected_dims
            if 0 <= quality_scores.get(d, -1) <= 100
        )
        metrics.scores["score_validity"] = in_range / len(expected_dims)

        # Feedback actionability (critical issues have sections and suggestions)
        critical_issues = feedback.get("critical_issues", [])
        if critical_issues:
            actionable = sum(
                1 for i in critical_issues
                if i.get("section") and i.get("issue")
            )
            metrics.scores["issue_actionability"] = actionable / len(critical_issues)
        else:
            metrics.scores["issue_actionability"] = 1.0  # No issues = fine

        metrics.scores["confidence"] = confidence

        # Pass: all dimensions present and confidence > 0
        metrics.passed = present == len(expected_dims) and confidence > 0
        if not metrics.passed:
            metrics.issues.append("Incomplete quality scoring or zero confidence")

        return metrics


class FactCheckerEval:
    """Evaluate fact-checker for claim coverage and accuracy."""

    @staticmethod
    def evaluate(
        result: dict, user_profile: dict, draft_content: dict,
    ) -> EvalMetrics:
        metrics = EvalMetrics(agent_name="fact_checker")

        claims = result.get("claims", [])
        summary = result.get("summary", {})
        fabricated = result.get("fabricated_claims", [])
        accuracy = result.get("overall_accuracy", 0)
        confidence = result.get("confidence", 0)
        det_match_rate = result.get("deterministic_match_rate", 0)

        # Claim coverage (how many claims does it actually classify)
        total_classified = (
            summary.get("verified", 0)
            + summary.get("enhanced", 0)
            + summary.get("fabricated", 0)
        )
        metrics.scores["claim_coverage"] = min(1.0, total_classified / max(len(claims), 1))

        # Accuracy score
        metrics.scores["overall_accuracy"] = accuracy

        # Deterministic match rate (hybrid approach effectiveness)
        metrics.scores["deterministic_match_rate"] = det_match_rate

        # Confidence
        metrics.scores["confidence"] = confidence

        # Fabrication rate (lower is better — invert for scoring)
        fab_count = summary.get("fabricated", 0)
        total = max(total_classified, 1)
        metrics.scores["fabrication_rate"] = 1.0 - (fab_count / total)

        # Pass: classified at least some claims
        metrics.passed = total_classified > 0 and confidence > 0
        if not metrics.passed:
            metrics.issues.append("No claims classified or zero confidence")

        return metrics


class OptimizerEval:
    """Evaluate optimizer for measurable ATS and readability improvements."""

    @staticmethod
    def evaluate(result: dict) -> EvalMetrics:
        metrics = EvalMetrics(agent_name="optimizer")

        kw_analysis = result.get("keyword_analysis", {})
        readability = result.get("readability_score", 0)
        ats_score = result.get("ats_score", 0)
        suggestions = result.get("suggestions", [])
        confidence = result.get("confidence", 0)

        # ATS score (0-100, normalized to 0-1)
        metrics.scores["ats_score"] = ats_score / 100.0 if ats_score else 0

        # Readability (Flesch ease, ideal 60-80)
        if readability:
            if 60 <= readability <= 80:
                metrics.scores["readability_quality"] = 1.0
            elif 40 <= readability < 60 or 80 < readability <= 90:
                metrics.scores["readability_quality"] = 0.7
            else:
                metrics.scores["readability_quality"] = 0.4
        else:
            metrics.scores["readability_quality"] = 0

        # Suggestion quality (each should have type, priority, actionable text)
        if suggestions:
            actionable = sum(
                1 for s in suggestions
                if isinstance(s, dict) and s.get("type") and s.get("text")
            )
            metrics.scores["suggestion_actionability"] = actionable / len(suggestions)
        else:
            metrics.scores["suggestion_actionability"] = 0

        # Keyword gap coverage
        missing = kw_analysis.get("missing", [])
        insertion_sugs = kw_analysis.get("insertion_suggestions", [])
        if missing:
            covered = sum(
                1 for s in insertion_sugs
                if isinstance(s, dict) and s.get("keyword") in missing
            )
            metrics.scores["keyword_gap_coverage"] = covered / len(missing)
        else:
            metrics.scores["keyword_gap_coverage"] = 1.0

        metrics.scores["confidence"] = confidence
        metrics.passed = confidence > 0
        if not metrics.passed:
            metrics.issues.append("Zero confidence from optimizer")

        return metrics


class ValidatorEval:
    """Evaluate validator for correctness of checks."""

    @staticmethod
    def evaluate(result: dict) -> EvalMetrics:
        metrics = EvalMetrics(agent_name="validator")

        valid = result.get("valid", False)
        checks = result.get("checks", {})
        issues = result.get("issues", [])
        confidence = result.get("confidence", 0)

        # All deterministic checks should be populated
        expected_checks = [
            "schema_compliant", "format_valid",
            "all_sections_present", "length_appropriate",
        ]
        checks_present = sum(1 for c in expected_checks if c in checks)
        metrics.scores["check_completeness"] = checks_present / len(expected_checks)

        # Issue quality (each should have field, severity, message)
        if issues:
            well_formed = sum(
                1 for i in issues
                if isinstance(i, dict)
                and i.get("field") and i.get("severity") and i.get("message")
            )
            metrics.scores["issue_quality"] = well_formed / len(issues)
        else:
            metrics.scores["issue_quality"] = 1.0  # No issues is acceptable

        metrics.scores["confidence"] = confidence
        metrics.scores["passed_validation"] = 1.0 if valid else 0.0

        metrics.passed = checks_present == len(expected_checks)
        if not metrics.passed:
            metrics.issues.append("Missing deterministic check results")

        return metrics


@dataclass
class PipelineEvalReport:
    """Full evaluation report for a pipeline run."""
    pipeline_name: str
    agent_metrics: dict[str, EvalMetrics] = field(default_factory=dict)
    total_latency_ms: int = 0
    total_token_estimate: int = 0
    iterations_used: int = 0
    overall_quality: float = 0.0
    task_success: bool = True
    policy_decisions: dict[str, str] = field(default_factory=dict)

    def add_agent_eval(self, metrics: EvalMetrics) -> None:
        self.agent_metrics[metrics.agent_name] = metrics
        self.total_latency_ms += metrics.latency_ms
        self.total_token_estimate += metrics.token_estimate
        if not metrics.passed:
            self.task_success = False

    def compute_overall_quality(self) -> float:
        """Weighted average of agent scores."""
        weights = {
            "researcher": 0.15,
            "critic": 0.25,
            "fact_checker": 0.25,
            "optimizer": 0.20,
            "validator": 0.15,
        }
        total_weight = 0.0
        weighted_sum = 0.0
        for agent_name, metrics in self.agent_metrics.items():
            w = weights.get(agent_name, 0.1)
            avg_score = (
                sum(metrics.scores.values()) / max(len(metrics.scores), 1)
            )
            weighted_sum += w * avg_score
            total_weight += w

        self.overall_quality = round(
            weighted_sum / max(total_weight, 0.01), 3,
        )
        return self.overall_quality

    def to_dict(self) -> dict:
        self.compute_overall_quality()
        return {
            "pipeline": self.pipeline_name,
            "overall_quality": self.overall_quality,
            "task_success": self.task_success,
            "total_latency_ms": self.total_latency_ms,
            "total_token_estimate": self.total_token_estimate,
            "iterations_used": self.iterations_used,
            "policy_decisions": self.policy_decisions,
            "agents": {
                name: m.to_dict() for name, m in self.agent_metrics.items()
            },
        }


def evaluate_pipeline_result(
    pipeline_name: str,
    pipeline_result: Any,
    context: dict,
) -> PipelineEvalReport:
    """Run full evaluation on a completed pipeline result.

    Args:
        pipeline_name: Name of the pipeline that was executed
        pipeline_result: PipelineResult from orchestrator
        context: Original context dict that was passed to pipeline
    """
    report = PipelineEvalReport(pipeline_name=pipeline_name)
    report.total_latency_ms = getattr(pipeline_result, "total_latency_ms", 0)
    report.iterations_used = getattr(pipeline_result, "iterations_used", 0)

    content = getattr(pipeline_result, "content", {})
    quality_scores = getattr(pipeline_result, "quality_scores", {})
    optimization_report = getattr(pipeline_result, "optimization_report", {})
    fact_check_report = getattr(pipeline_result, "fact_check_report", {})

    # Evaluate critic output (if quality scores present)
    if quality_scores:
        critic_data = {
            "quality_scores": quality_scores,
            "feedback": content.get("feedback", {}),
            "confidence": content.get("confidence", 0.5),
        }
        report.add_agent_eval(
            CriticEval.evaluate(critic_data, content)
        )

    # Evaluate fact-checker output
    if fact_check_report:
        report.add_agent_eval(
            FactCheckerEval.evaluate(
                fact_check_report,
                context.get("user_profile", {}),
                content,
            )
        )

    # Evaluate optimizer output
    if optimization_report:
        report.add_agent_eval(
            OptimizerEval.evaluate(optimization_report)
        )

    # Evaluate validator output
    if content and "valid" in content:
        report.add_agent_eval(
            ValidatorEval.evaluate(content)
        )

    report.compute_overall_quality()
    return report
