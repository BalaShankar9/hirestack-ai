"""
Pipeline observability — structured metrics emitted at pipeline boundaries.

Captures contract drift, evidence coverage, quality signals, cost tracking,
cache efficiency, and model routing decisions in a single summary record.
All metrics are warning-level log events (no external dependencies required).
The summary can be persisted alongside the trace record for offline analysis.
"""
from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger("hirestack.agents.observability")


class PipelineMetrics:
    """Collects and emits structured observability metrics for a pipeline run."""

    def __init__(self, pipeline_id: str, pipeline_name: str, user_id: str):
        self._citation_coverage: Optional[float] = None
        self._citation_coverage_threshold: float = 0.6
        self.pipeline_id = pipeline_id
        self.pipeline_name = pipeline_name
        self.user_id = user_id
        self._contract_issues: dict[str, list[str]] = {}
        self._stage_latencies: dict[str, int] = {}
        self._evidence_stats: dict[str, Any] = {}
        self._quality_scores: dict[str, float] = {}
        self._final_analysis: dict[str, Any] = {}
        # Part 2: cost, cache, and model routing tracking
        self._cost_snapshot_start: dict[str, Any] = {}
        self._cost_snapshot_end: dict[str, Any] = {}
        self._model_decisions: list[dict[str, str]] = []
        self._tool_timeouts: list[str] = []

    # ── Contract drift tracking ───────────────────────────────────

    def record_contract_issues(self, stage: str, issues: list[str]) -> None:
        """Record contract validation issues for a stage."""
        if issues:
            self._contract_issues[stage] = issues

    def record_stage_latency(self, stage: str, latency_ms: int) -> None:
        """Record stage execution time."""
        self._stage_latencies[stage] = latency_ms

    # ── Evidence coverage ─────────────────────────────────────────

    def record_citation_coverage(self, coverage: Optional[float], threshold: float = 0.6) -> None:
        """Record claim->evidence link coverage and emit SLO breach warning.

        coverage: fraction of fact-check claims linked to >=1 evidence id (0.0-1.0)
        threshold: minimum acceptable coverage; below this we log a structured
                   warning so on-call can detect citation linker degradation
                   without waiting for a user-visible quality drop.
        None means no citations were produced (skip case) and is not scored.
        """
        self._citation_coverage = coverage
        self._citation_coverage_threshold = threshold
        if coverage is not None and coverage < threshold:
            logger.warning(
                "pipeline_citation_coverage_slo_breach",
                pipeline_id=self.pipeline_id,
                pipeline=self.pipeline_name,
                user_id=self.user_id,
                coverage=coverage,
                threshold=threshold,
                gap=round(threshold - coverage, 3),
            )

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

    # ── Cost & cache tracking (Part 2) ────────────────────────────

    def snapshot_cost_start(self) -> None:
        """Capture daily usage counters BEFORE the pipeline runs."""
        try:
            from ai_engine.client import get_daily_usage
            self._cost_snapshot_start = get_daily_usage()
        except Exception:
            self._cost_snapshot_start = {}

    def snapshot_cost_end(self) -> None:
        """Capture daily usage counters AFTER the pipeline completes."""
        try:
            from ai_engine.client import get_daily_usage
            self._cost_snapshot_end = get_daily_usage()
        except Exception:
            self._cost_snapshot_end = {}

    def record_model_decision(self, stage: str, model: str, task_type: str) -> None:
        """Record which model was used for a given stage."""
        self._model_decisions.append({
            "stage": stage,
            "model": model,
            "task_type": task_type,
        })

    def record_tool_timeout(self, tool_name: str) -> None:
        """Record a tool that timed out during execution."""
        self._tool_timeouts.append(tool_name)

    def _compute_pipeline_cost(self) -> dict[str, Any]:
        """Compute cost delta between start and end snapshots."""
        if not self._cost_snapshot_start or not self._cost_snapshot_end:
            return {}
        tokens_used = (
            self._cost_snapshot_end.get("total_tokens", 0)
            - self._cost_snapshot_start.get("total_tokens", 0)
        )
        cost_usd = round(
            self._cost_snapshot_end.get("total_cost_usd", 0)
            - self._cost_snapshot_start.get("total_cost_usd", 0),
            5,
        )
        calls_made = (
            self._cost_snapshot_end.get("total_calls", 0)
            - self._cost_snapshot_start.get("total_calls", 0)
        )
        cache_hits = (
            self._cost_snapshot_end.get("cache_hits", 0)
            - self._cost_snapshot_start.get("cache_hits", 0)
        )
        return {
            "tokens_used": tokens_used,
            "cost_usd": cost_usd,
            "llm_calls": calls_made,
            "cache_hits": cache_hits,
            "cache_hit_rate": round(
                cache_hits / max(calls_made + cache_hits, 1), 3
            ),
        }

    # ── Final analysis ────────────────────────────────────────────

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
            "citation_coverage": self._citation_coverage,
            "citation_coverage_threshold": self._citation_coverage_threshold,
            "quality_scores": self._quality_scores,
            "final_analysis": self._final_analysis,
            "cost": self._compute_pipeline_cost(),
            "model_decisions": self._model_decisions,
            "tool_timeouts": self._tool_timeouts,
        }

    def emit(self) -> dict[str, Any]:
        """Build and log the pipeline summary. Returns the summary dict."""
        summary = self.build_summary()
        drift_count = summary["contract_drift"]["total_issue_count"]
        cost = summary.get("cost", {})

        log_kwargs = dict(
            pipeline=self.pipeline_name,
            evidence_coverage=summary["evidence"].get("coverage_ratio", 0),
            total_latency_ms=summary["total_latency_ms"],
            cost_usd=cost.get("cost_usd", 0),
            llm_calls=cost.get("llm_calls", 0),
            cache_hit_rate=cost.get("cache_hit_rate", 0),
            tool_timeouts=len(self._tool_timeouts),
        )

        if drift_count > 0:
            logger.warning(
                "pipeline_observability_summary",
                drift_stages=summary["contract_drift"]["stages_with_issues"],
                drift_count=drift_count,
                **log_kwargs,
            )
        else:
            logger.info("pipeline_observability_summary", **log_kwargs)

        return summary
