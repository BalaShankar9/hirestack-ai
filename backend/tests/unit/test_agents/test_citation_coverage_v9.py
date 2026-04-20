"""Tests for v9 citation_coverage metric on PipelineResult.

Anchors the new instrumentation so future refactors don't silently
drop the metric.  Pipelines depend on this number to detect citation
linking degradation.
"""
from __future__ import annotations

import inspect

from ai_engine.agents.orchestrator import (
    PipelineResult,
    _compute_citation_coverage,
)


class TestComputeCitationCoverage:
    def test_returns_none_when_no_citations(self):
        assert _compute_citation_coverage(None) is None
        assert _compute_citation_coverage([]) is None

    def test_returns_one_when_all_claims_grounded(self):
        citations = [
            {"claim_text": "a", "evidence_ids": ["ev_1"]},
            {"claim_text": "b", "evidence_ids": ["ev_2", "ev_3"]},
        ]
        assert _compute_citation_coverage(citations) == 1.0

    def test_returns_zero_when_no_claims_grounded(self):
        citations = [
            {"claim_text": "a", "evidence_ids": []},
            {"claim_text": "b", "evidence_ids": []},
        ]
        assert _compute_citation_coverage(citations) == 0.0

    def test_returns_partial_fraction(self):
        citations = [
            {"claim_text": "a", "evidence_ids": ["ev_1"]},
            {"claim_text": "b", "evidence_ids": []},
            {"claim_text": "c", "evidence_ids": ["ev_2"]},
            {"claim_text": "d", "evidence_ids": []},
        ]
        assert _compute_citation_coverage(citations) == 0.5

    def test_treats_missing_key_as_ungrounded(self):
        citations = [
            {"claim_text": "a"},  # no evidence_ids key at all
            {"claim_text": "b", "evidence_ids": ["ev_1"]},
        ]
        assert _compute_citation_coverage(citations) == 0.5


class TestPipelineResultExposesCoverageField:
    def test_field_exists_on_dataclass(self):
        # Catches accidental removal of the field during a refactor
        result = PipelineResult(
            content={},
            quality_scores={},
            optimization_report={},
            fact_check_report={},
            iterations_used=0,
            total_latency_ms=0,
            trace_id="t",
            citation_coverage=0.75,
        )
        assert result.citation_coverage == 0.75

    def test_field_defaults_to_none(self):
        result = PipelineResult(
            content={},
            quality_scores={},
            optimization_report={},
            fact_check_report={},
            iterations_used=0,
            total_latency_ms=0,
            trace_id="t",
        )
        assert result.citation_coverage is None

    def test_orchestrator_populates_coverage_in_final_result(self):
        # Regression guard: the final return path of execute() must wire
        # citation_coverage from _compute_citation_coverage(citations).
        # If a refactor drops the kwarg, this test fails.
        from ai_engine.agents import orchestrator
        src = inspect.getsource(orchestrator)
        assert "citation_coverage=_compute_citation_coverage(citations)" in src, (
            "execute() final return must compute citation_coverage from "
            "the citations list — instrumentation regression"
        )
