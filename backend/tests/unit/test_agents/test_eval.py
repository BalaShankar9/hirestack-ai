# backend/tests/unit/test_agents/test_eval.py
"""Tests for the agent evaluation harness."""
import pytest
from ai_engine.agents.eval import (
    EvalMetrics,
    ResearcherEval,
    CriticEval,
    FactCheckerEval,
    OptimizerEval,
    ValidatorEval,
    PipelineEvalReport,
    evaluate_pipeline_result,
)


# ═══════════════════════════════════════════════════════════════════════
#  EvalMetrics
# ═══════════════════════════════════════════════════════════════════════

class TestEvalMetrics:
    def test_to_dict(self):
        em = EvalMetrics(agent_name="test", scores={"a": 0.9}, passed=True, issues=["x"])
        d = em.to_dict()
        assert d["agent"] == "test"
        assert d["scores"] == {"a": 0.9}
        assert d["passed"] is True
        assert "x" in d["issues"]


# ═══════════════════════════════════════════════════════════════════════
#  ResearcherEval
# ═══════════════════════════════════════════════════════════════════════

class TestResearcherEval:
    def test_high_coverage_passes(self):
        result = {
            "coverage_score": 0.8,
            "tools_used": ["parse_jd", "extract_profile_evidence", "compute_keyword_overlap"],
            "keyword_priority": ["Python", "AWS", "Docker", "FastAPI", "K8s", "React", "SQL", "Go", "CI/CD", "Linux"],
            "key_signals": ["5 years exp", "cloud certs", "team lead", "startup", "scale"],
        }
        metrics = ResearcherEval.evaluate(result, {})
        assert metrics.passed is True
        assert metrics.scores["coverage"] == 0.8
        assert metrics.scores["tool_utilization"] == 1.0  # 3/3
        assert metrics.scores["keyword_density"] == 1.0  # 10/10
        assert metrics.scores["signal_count"] == 1.0  # 5/5

    def test_low_coverage_fails(self):
        result = {"coverage_score": 0.3, "tools_used": [], "keyword_priority": [], "key_signals": []}
        metrics = ResearcherEval.evaluate(result, {})
        assert metrics.passed is False
        assert len(metrics.issues) > 0

    def test_empty_result(self):
        metrics = ResearcherEval.evaluate({}, {})
        assert metrics.passed is False
        assert metrics.scores["coverage"] == 0


# ═══════════════════════════════════════════════════════════════════════
#  CriticEval
# ═══════════════════════════════════════════════════════════════════════

class TestCriticEval:
    def test_complete_scores_pass(self):
        result = {
            "quality_scores": {"impact": 85, "clarity": 90, "tone_match": 88, "completeness": 82},
            "feedback": {"critical_issues": [{"section": "intro", "issue": "weak opener"}]},
            "confidence": 0.9,
        }
        metrics = CriticEval.evaluate(result, {})
        assert metrics.passed is True
        assert metrics.scores["score_completeness"] == 1.0
        assert metrics.scores["score_validity"] == 1.0
        assert metrics.scores["confidence"] == 0.9

    def test_missing_dimensions_fail(self):
        result = {
            "quality_scores": {"impact": 85},  # Missing 3 dimensions
            "feedback": {},
            "confidence": 0.7,
        }
        metrics = CriticEval.evaluate(result, {})
        assert metrics.passed is False
        assert metrics.scores["score_completeness"] == 0.25

    def test_zero_confidence_fails(self):
        result = {
            "quality_scores": {"impact": 85, "clarity": 90, "tone_match": 88, "completeness": 82},
            "confidence": 0,
        }
        metrics = CriticEval.evaluate(result, {})
        assert metrics.passed is False


# ═══════════════════════════════════════════════════════════════════════
#  FactCheckerEval
# ═══════════════════════════════════════════════════════════════════════

class TestFactCheckerEval:
    def test_good_fact_check(self):
        result = {
            "claims": [{"text": "Led 5 eng"}, {"text": "AWS cert"}],
            "summary": {"verified": 2, "enhanced": 0, "fabricated": 0},
            "fabricated_claims": [],
            "overall_accuracy": 0.95,
            "confidence": 0.9,
            "deterministic_match_rate": 0.8,
        }
        metrics = FactCheckerEval.evaluate(result, {}, {})
        assert metrics.passed is True
        assert metrics.scores["overall_accuracy"] == 0.95
        assert metrics.scores["fabrication_rate"] == 1.0  # No fabrications

    def test_fabrications_detected(self):
        result = {
            "claims": [{"text": "c1"}, {"text": "c2"}, {"text": "c3"}],
            "summary": {"verified": 1, "enhanced": 0, "fabricated": 2},
            "fabricated_claims": [{"text": "c2"}, {"text": "c3"}],
            "overall_accuracy": 0.33,
            "confidence": 0.85,
        }
        metrics = FactCheckerEval.evaluate(result, {}, {})
        assert metrics.passed is True
        assert metrics.scores["fabrication_rate"] == pytest.approx(1.0 / 3.0)

    def test_no_claims_fails(self):
        result = {"claims": [], "summary": {}, "confidence": 0}
        metrics = FactCheckerEval.evaluate(result, {}, {})
        assert metrics.passed is False


# ═══════════════════════════════════════════════════════════════════════
#  OptimizerEval
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizerEval:
    def test_good_optimization(self):
        result = {
            "keyword_analysis": {"missing": ["AWS"], "insertion_suggestions": [{"keyword": "AWS", "loc": "skills"}]},
            "readability_score": 65,
            "ats_score": 80,
            "suggestions": [{"type": "add_keyword", "text": "Add AWS", "priority": "high"}],
            "confidence": 0.88,
        }
        metrics = OptimizerEval.evaluate(result)
        assert metrics.passed is True
        assert metrics.scores["ats_score"] == 0.8
        assert metrics.scores["readability_quality"] == 1.0  # 65 is in 60-80
        assert metrics.scores["keyword_gap_coverage"] == 1.0
        assert metrics.scores["suggestion_actionability"] == 1.0

    def test_poor_readability(self):
        result = {"readability_score": 20, "ats_score": 0, "suggestions": [], "confidence": 0.5}
        metrics = OptimizerEval.evaluate(result)
        assert metrics.scores["readability_quality"] == 0.4

    def test_zero_confidence(self):
        result = {"confidence": 0}
        metrics = OptimizerEval.evaluate(result)
        assert metrics.passed is False


# ═══════════════════════════════════════════════════════════════════════
#  ValidatorEval
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorEval:
    def test_complete_validation(self):
        result = {
            "valid": True,
            "checks": {
                "schema_compliant": True,
                "format_valid": True,
                "all_sections_present": True,
                "length_appropriate": True,
            },
            "issues": [],
            "confidence": 0.95,
        }
        metrics = ValidatorEval.evaluate(result)
        assert metrics.passed is True
        assert metrics.scores["check_completeness"] == 1.0
        assert metrics.scores["passed_validation"] == 1.0

    def test_missing_checks_fail(self):
        result = {"valid": True, "checks": {"schema_compliant": True}, "issues": [], "confidence": 0.8}
        metrics = ValidatorEval.evaluate(result)
        assert metrics.passed is False
        assert metrics.scores["check_completeness"] == 0.25

    def test_issues_quality(self):
        result = {
            "valid": False,
            "checks": {"schema_compliant": True, "format_valid": True, "all_sections_present": True, "length_appropriate": True},
            "issues": [
                {"field": "html", "severity": "critical", "message": "Too short"},
                {"field": "name", "severity": "warning", "message": "Missing"},
            ],
            "confidence": 0.7,
        }
        metrics = ValidatorEval.evaluate(result)
        assert metrics.scores["issue_quality"] == 1.0


# ═══════════════════════════════════════════════════════════════════════
#  PipelineEvalReport
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineEvalReport:
    def test_add_agent_eval(self):
        report = PipelineEvalReport(pipeline_name="test")
        m = EvalMetrics(agent_name="critic", scores={"a": 0.8}, latency_ms=100)
        report.add_agent_eval(m)
        assert "critic" in report.agent_metrics
        assert report.total_latency_ms == 100

    def test_compute_overall_quality(self):
        report = PipelineEvalReport(pipeline_name="test")
        report.add_agent_eval(EvalMetrics(agent_name="critic", scores={"s": 0.8}))
        report.add_agent_eval(EvalMetrics(agent_name="validator", scores={"s": 0.6}))
        q = report.compute_overall_quality()
        assert 0 < q < 1

    def test_task_success_false_on_failed_agent(self):
        report = PipelineEvalReport(pipeline_name="test")
        report.add_agent_eval(EvalMetrics(agent_name="critic", passed=False))
        assert report.task_success is False

    def test_to_dict(self):
        report = PipelineEvalReport(pipeline_name="test")
        report.add_agent_eval(EvalMetrics(agent_name="critic", scores={"a": 0.9}))
        d = report.to_dict()
        assert d["pipeline"] == "test"
        assert "critic" in d["agents"]
        assert "overall_quality" in d


# ═══════════════════════════════════════════════════════════════════════
#  evaluate_pipeline_result integration
# ═══════════════════════════════════════════════════════════════════════

class TestEvaluatePipelineResult:
    def test_evaluates_full_result(self):
        class FakeResult:
            total_latency_ms = 500
            iterations_used = 1
            content = {
                "valid": True,
                "checks": {"schema_compliant": True, "format_valid": True, "all_sections_present": True, "length_appropriate": True},
                "issues": [],
                "confidence": 0.9,
            }
            quality_scores = {"impact": 85, "clarity": 90, "tone_match": 88, "completeness": 80}
            optimization_report = {"ats_score": 75, "readability_score": 65, "suggestions": [], "confidence": 0.8}
            fact_check_report = {
                "claims": [{"text": "c1"}],
                "summary": {"verified": 1, "enhanced": 0, "fabricated": 0},
                "overall_accuracy": 1.0,
                "confidence": 0.9,
            }

        report = evaluate_pipeline_result("cv_generation", FakeResult(), {"user_profile": {}})
        assert report.pipeline_name == "cv_generation"
        assert report.overall_quality > 0

    def test_handles_empty_result(self):
        class FakeResult:
            total_latency_ms = 0
            iterations_used = 0
            content = {}
            quality_scores = {}
            optimization_report = {}
            fact_check_report = {}

        report = evaluate_pipeline_result("test", FakeResult(), {})
        assert report.overall_quality == 0
