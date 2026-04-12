"""Tests for key normalization, _format_response, and related generate.py helpers."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.routes.generate import (  # noqa: E402
    _CAMEL_TO_SNAKE,
    _DEFAULT_REQUESTED_MODULES,
    _IDENTITY_KEYS,
    _SNAKE_TO_CAMEL,
    _normalize_requested_modules,
)
from app.services.pipeline_runtime import PipelineRuntime  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════
#  Key mapping integrity
# ═══════════════════════════════════════════════════════════════════════

class TestKeyMappings:
    def test_snake_to_camel_all_keys_present(self):
        assert _SNAKE_TO_CAMEL["cover_letter"] == "coverLetter"
        assert _SNAKE_TO_CAMEL["personal_statement"] == "personalStatement"
        assert _SNAKE_TO_CAMEL["learning_plan"] == "learningPlan"
        assert _SNAKE_TO_CAMEL["gap_analysis"] == "gaps"

    def test_camel_to_snake_reverse(self):
        for snake, camel in _SNAKE_TO_CAMEL.items():
            assert _CAMEL_TO_SNAKE[camel] == snake

    def test_identity_keys_consistent(self):
        """Identity keys should NOT appear in the snake→camel mapping."""
        for key in _IDENTITY_KEYS:
            assert key not in _SNAKE_TO_CAMEL

    def test_default_modules_use_camel_case(self):
        """Internal canonical form is camelCase."""
        for mod in _DEFAULT_REQUESTED_MODULES:
            assert "_" not in mod or mod in _IDENTITY_KEYS, (
                f"Module '{mod}' has underscore but is not in identity keys"
            )


# ═══════════════════════════════════════════════════════════════════════
#  _normalize_requested_modules tests
# ═══════════════════════════════════════════════════════════════════════

class TestNormalizeRequestedModules:
    def test_none_returns_defaults(self):
        result = _normalize_requested_modules(None)
        assert result == list(_DEFAULT_REQUESTED_MODULES)

    def test_empty_list_returns_defaults(self):
        result = _normalize_requested_modules([])
        assert result == list(_DEFAULT_REQUESTED_MODULES)

    def test_camel_case_passthrough(self):
        result = _normalize_requested_modules(["cv", "coverLetter", "gaps"])
        assert result == ["cv", "coverLetter", "gaps"]

    def test_snake_case_converted(self):
        result = _normalize_requested_modules(["cv", "cover_letter", "personal_statement"])
        assert "coverLetter" in result
        assert "personalStatement" in result
        assert "cover_letter" not in result
        assert "personal_statement" not in result

    def test_mixed_formats(self):
        result = _normalize_requested_modules(["cv", "cover_letter", "gaps", "personalStatement"])
        assert "cv" in result
        assert "coverLetter" in result
        assert "gaps" in result
        assert "personalStatement" in result

    def test_deduplication(self):
        """Same module in both formats should not appear twice."""
        result = _normalize_requested_modules(["coverLetter", "cover_letter"])
        assert result.count("coverLetter") == 1

    def test_unknown_modules_rejected(self):
        result = _normalize_requested_modules(["cv", "nonexistent_module", "gaps"])
        assert "nonexistent_module" not in result
        assert "cv" in result
        assert "gaps" in result

    def test_all_unknown_falls_back_to_defaults(self):
        result = _normalize_requested_modules(["totally_fake", "not_a_module"])
        assert result == list(_DEFAULT_REQUESTED_MODULES)

    def test_learning_plan_conversion(self):
        result = _normalize_requested_modules(["learning_plan"])
        assert "learningPlan" in result

    def test_gap_analysis_conversion(self):
        result = _normalize_requested_modules(["gap_analysis"])
        assert "gaps" in result

    def test_order_preserved(self):
        result = _normalize_requested_modules(["portfolio", "cv", "gaps"])
        assert result == ["portfolio", "cv", "gaps"]


# ═══════════════════════════════════════════════════════════════════════
#  _format_response tests (PipelineRuntime static method)
# ═══════════════════════════════════════════════════════════════════════

class TestFormatResponse:
    """Test the extended _format_response in PipelineRuntime."""

    _BASE_KWARGS = dict(
        benchmark_data={
            "ideal_profile": {"summary": "Ideal senior dev"},
            "ideal_skills": [{"name": "Python", "level": "expert", "importance": "critical"}],
            "ideal_experience": [],
            "scoring_weights": {},
        },
        gap_analysis={
            "compatibility_score": 72,
            "strengths": [{"area": "Python", "evidence": "5 years"}],
            "skill_gaps": [
                {"skill": "Kubernetes", "current_level": "none",
                 "required_level": "intermediate", "gap_severity": "moderate",
                 "recommendation": "Learn K8s basics"},
            ],
            "recommendations": [{"title": "Study K8s"}],
            "missing_keywords": ["Kubernetes"],
        },
        roadmap={"phases": [{"title": "Month 1"}]},
        cv_html="<div>CV HTML</div>",
        cl_html="<div>Cover Letter HTML</div>",
        ps_html="<div>Personal Statement HTML</div>",
        portfolio_html="<div>Portfolio HTML</div>",
        validation={"cv": {"valid": True, "qualityScore": 85}},
        keywords=["Python", "Kubernetes", "AWS"],
        job_title="Senior Engineer",
        benchmark_cv_html="<div>Benchmark CV</div>",
    )

    def test_has_flat_html_keys(self):
        """Response must include flat HTML keys for persistence compatibility."""
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        assert result["cvHtml"] == "<div>CV HTML</div>"
        assert result["coverLetterHtml"] == "<div>Cover Letter HTML</div>"
        assert result["personalStatementHtml"] == "<div>Personal Statement HTML</div>"
        assert result["portfolioHtml"] == "<div>Portfolio HTML</div>"

    def test_has_nested_documents(self):
        """Response must include nested documents dict for backward compat."""
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        docs = result["documents"]
        assert docs["cv"] == "<div>CV HTML</div>"
        assert docs["coverLetter"] == "<div>Cover Letter HTML</div>"
        assert docs["personalStatement"] == "<div>Personal Statement HTML</div>"
        assert docs["portfolio"] == "<div>Portfolio HTML</div>"

    def test_has_scorecard(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        scorecard = result["scorecard"]
        assert "overall" in scorecard
        assert "dimensions" in scorecard
        assert isinstance(scorecard["dimensions"], list)
        assert len(scorecard["dimensions"]) >= 4

    def test_scores_include_extended_fields(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        scores = result["scores"]
        for key in ("match", "atsReadiness", "recruiterScan", "evidenceStrength",
                     "cv", "coverLetter", "gaps", "benchmark"):
            assert key in scores, f"Missing score key: {key}"

    def test_scores_overall_from_compatibility(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        assert result["scores"]["overall"] == 72

    def test_gaps_structure(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        gaps = result["gaps"]
        assert "missingKeywords" in gaps
        assert "strengths" in gaps
        assert "recommendations" in gaps
        assert "gaps" in gaps
        assert gaps["compatibility"] == 72

    def test_benchmark_structure(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        bench = result["benchmark"]
        assert bench["summary"] == "Ideal senior dev"
        assert bench["benchmarkCvHtml"] == "<div>Benchmark CV</div>"
        assert "keywords" in bench
        assert "rubric" in bench

    def test_validation_passed_through(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        assert result["validation"]["cv"]["valid"] is True

    def test_learning_plan_present(self):
        result = PipelineRuntime._format_response(**self._BASE_KWARGS)
        assert result["learningPlan"]["phases"][0]["title"] == "Month 1"

    def test_empty_inputs_no_crash(self):
        """Format response handles empty/missing data gracefully."""
        result = PipelineRuntime._format_response(
            benchmark_data={},
            gap_analysis={},
            roadmap={},
            cv_html="",
            cl_html="",
            ps_html="",
            portfolio_html="",
            validation={},
            keywords=[],
            job_title="Test",
        )
        assert result["scores"]["overall"] == 50  # default
        assert result["cvHtml"] == ""
        assert result["documents"]["cv"] == ""

    def test_gap_severity_mapping(self):
        """Critical gap_severity maps to 'high'."""
        kwargs = dict(self._BASE_KWARGS)
        kwargs["gap_analysis"] = {
            "compatibility_score": 60,
            "skill_gaps": [
                {"skill": "Security", "current_level": "none",
                 "required_level": "expert", "gap_severity": "critical",
                 "recommendation": "Get certified"},
            ],
        }
        result = PipelineRuntime._format_response(**kwargs)
        gap_items = result["gaps"]["gaps"]
        assert gap_items[0]["severity"] == "high"
