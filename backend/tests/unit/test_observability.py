# backend/tests/unit/test_observability.py
"""Tests for Phase 6: pipeline observability metrics."""
from ai_engine.agents.observability import PipelineMetrics


class TestPipelineMetrics:
    def test_empty_metrics_summary(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        summary = m.build_summary()
        assert summary["pipeline_id"] == "pid"
        assert summary["pipeline_name"] == "cv_generation"
        assert summary["contract_drift"]["total_issue_count"] == 0
        assert summary["total_latency_ms"] == 0

    def test_contract_drift_tracking(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_contract_issues("researcher", ["missing key: industry"])
        m.record_contract_issues("drafter", [])
        summary = m.build_summary()
        assert summary["contract_drift"]["stages_with_issues"] == ["researcher"]
        assert summary["contract_drift"]["total_issue_count"] == 1

    def test_stage_latency_tracking(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_stage_latency("researcher", 500)
        m.record_stage_latency("drafter", 1200)
        summary = m.build_summary()
        assert summary["total_latency_ms"] == 1700
        assert summary["stage_latencies"]["researcher"] == 500

    def test_evidence_stats(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_evidence_stats(
            total_items=10, cited_count=7,
            tier_distribution={"verbatim": 5, "derived": 3, "inferred": 2},
        )
        summary = m.build_summary()
        assert summary["evidence"]["coverage_ratio"] == 0.7
        assert summary["evidence"]["tier_distribution"]["verbatim"] == 5

    def test_quality_scores(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_quality_scores({"impact": 85, "clarity": 90})
        summary = m.build_summary()
        assert summary["quality_scores"]["impact"] == 85

    def test_emit_returns_summary(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_contract_issues("researcher", ["issue1"])
        summary = m.emit()
        assert summary["contract_drift"]["total_issue_count"] == 1

    def test_zero_evidence_coverage_ratio(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_evidence_stats(total_items=0, cited_count=0, tier_distribution={})
        summary = m.build_summary()
        assert summary["evidence"]["coverage_ratio"] == 0
