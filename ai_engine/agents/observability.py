"""
Pipeline observability — structured metrics emitted at pipeline boundaries.

Captures contract drift, evidence coverage, and quality signals in a single
summary record. All metrics are warning-level log events (no external
dependencies required). The summary can be persisted alongside the trace
record for offline analysis.
"""
from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.observability")


class PipelineMetrics:
    """Collects and emits structured observability metrics for a pipeline run."""

    def __init__(self, pipeline_id: str, pipeline_name: str, user_id: str):
        self.pipeline_id = pipeline_id
        self.pipeline_name = pipeline_name
        self.user_id = user_id
        self._contract_issues: dict[str, list[str]] = {}
        self._stage_latencies: dict[str, int] = {}
        self._evidence_stats: dict[str, Any] = {}
        self._quality_scores: dict[str, float] = {}
        self._final_analysis: dict[str, Any] = {}

    # ── Contract drift tracking ───────────────────────────────────

    def record_contract_issues(self, stage: str, issues: list[str]) -> None:
        """Record contract validation issues for a stage."""
        if issues:
            self._contract_issues[stage] = issues

    def record_stage_latency(self, stage: str, latency_ms: int) -> None:
        """Record stage execution time."""
        self._stage_latencies[stage] = latency_ms

    # ── Evidence coverage ─────────────────────────────────────────

    def record_evidence_stats(
        self,
        total_items: int,
        cited_count: int,
        tier_distribution: dict[str, int],
    ) -> None:
        """Record evidence ledger statistics."""
        self._evidence_stats = {
            "total_items": total_items,
            "cited_count": cited_count,
            "coverage_ratio": round(cited_count / max(total_items, 1), 3),
            "tier_distribution": tier_distribution,
        }

    def record_quality_scores(self, scores: dict[str, float]) -> None:
        """Record final quality scores from the critic."""
        self._quality_scores = dict(scores)

    def record_final_analysis(
        self,
        initial_ats_score: float,
        final_ats_score: float,
        keyword_gap_delta: float,
        readability_delta: float,
        residual_issue_count: int,
    ) -> None:
        """Record final optimization analysis deltas."""
        self._final_analysis = {
            "initial_ats_score": initial_ats_score,
            "final_ats_score": final_ats_score,
            "keyword_gap_delta": keyword_gap_delta,
            "readability_delta": readability_delta,
            "optimizer_residual_issue_count": residual_issue_count,
        }

    # ── Summary emission ──────────────────────────────────────────

    def build_summary(self) -> dict[str, Any]:
        """Build a structured summary of all collected metrics."""
        total_latency = sum(self._stage_latencies.values())
        stages_with_drift = list(self._contract_issues.keys())

        return {
            "pipeline_id": self.pipeline_id,
            "pipeline_name": self.pipeline_name,
            "user_id": self.user_id,
            "total_latency_ms": total_latency,
            "stage_latencies": self._stage_latencies,
            "contract_drift": {
                "stages_with_issues": stages_with_drift,
                "total_issue_count": sum(
                    len(v) for v in self._contract_issues.values()
                ),
                "details": self._contract_issues,
            },
            "evidence": self._evidence_stats,
            "quality_scores": self._quality_scores,
            "final_analysis": self._final_analysis,
        }

    def emit(self) -> dict[str, Any]:
        """Build and log the pipeline summary. Returns the summary dict."""
        summary = self.build_summary()
        drift_count = summary["contract_drift"]["total_issue_count"]

        if drift_count > 0:
            logger.warning(
                "pipeline_observability_summary",
                pipeline=self.pipeline_name,
                drift_stages=summary["contract_drift"]["stages_with_issues"],
                drift_count=drift_count,
                evidence_coverage=summary["evidence"].get("coverage_ratio", 0),
                total_latency_ms=summary["total_latency_ms"],
            )
        else:
            logger.info(
                "pipeline_observability_summary",
                pipeline=self.pipeline_name,
                evidence_coverage=summary["evidence"].get("coverage_ratio", 0),
                total_latency_ms=summary["total_latency_ms"],
            )

        return summary
