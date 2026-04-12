# backend/tests/unit/test_contracts.py
"""Tests for Phase 4: contract validation and tool normalization."""
import pytest
from ai_engine.agents.contracts import (
    ContractViolation,
    validate_researcher_output,
    validate_drafter_output,
    validate_critic_output,
    validate_optimizer_output,
    validate_fact_checker_output,
    validate_validator_output,
    validate_pipeline_result,
    validate_stage_output,
)
from ai_engine.agents.tool_normalizer import (
    normalize_tool_output,
    normalize_all_tool_results,
)


# ═══════════════════════════════════════════════════════════════════════
#  Researcher contract
# ═══════════════════════════════════════════════════════════════════════

class TestResearcherContract:
    def test_valid_output(self):
        content = {
            "industry": "tech",
            "keyword_priority": ["Python", "AWS"],
            "key_signals": ["remote"],
            "coverage_score": 0.85,
            "tool_results": {"compute_keyword_overlap": {}},
        }
        assert validate_researcher_output(content) == []

    def test_missing_keys(self):
        issues = validate_researcher_output({})
        assert any("Missing required keys" in i for i in issues)

    def test_bad_coverage_score_type(self):
        content = {
            "industry": "tech",
            "keyword_priority": [],
            "key_signals": [],
            "coverage_score": "high",
            "tool_results": {},
        }
        issues = validate_researcher_output(content)
        assert any("coverage_score must be numeric" in i for i in issues)

    def test_bad_tool_results_type(self):
        content = {
            "industry": "tech",
            "keyword_priority": [],
            "key_signals": [],
            "coverage_score": 0.5,
            "tool_results": "not a dict",
        }
        issues = validate_researcher_output(content)
        assert any("tool_results must be a dict" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  Drafter contract
# ═══════════════════════════════════════════════════════════════════════

class TestDrafterContract:
    def test_valid_output(self):
        assert validate_drafter_output({"html": "<p>CV</p>"}) == []

    def test_missing_html(self):
        issues = validate_drafter_output({"text": "some text"})
        assert any("Missing required keys" in i for i in issues)

    def test_html_wrong_type(self):
        issues = validate_drafter_output({"html": 42})
        assert any("html must be a string" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  Critic contract
# ═══════════════════════════════════════════════════════════════════════

class TestCriticContract:
    def test_valid_output(self):
        content = {
            "quality_scores": {
                "impact": 85,
                "clarity": 90,
                "tone_match": 80,
                "completeness": 75,
            },
            "needs_revision": False,
            "feedback": {"critical_issues": []},
            "confidence": 0.92,
        }
        assert validate_critic_output(content) == []

    def test_missing_quality_dimensions(self):
        content = {
            "quality_scores": {"impact": 85},
            "needs_revision": False,
            "feedback": {"critical_issues": []},
            "confidence": 0.9,
        }
        issues = validate_critic_output(content)
        assert any("clarity" in i for i in issues)
        assert any("tone_match" in i for i in issues)

    def test_missing_critical_issues_in_feedback(self):
        content = {
            "quality_scores": {"impact": 85, "clarity": 90, "tone_match": 80, "completeness": 75},
            "needs_revision": False,
            "feedback": {"general": "looks good"},
            "confidence": 0.9,
        }
        issues = validate_critic_output(content)
        assert any("critical_issues" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  Optimizer contract
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizerContract:
    def test_valid_output(self):
        content = {
            "keyword_analysis": {"present": ["Python"], "missing": ["AWS"]},
            "readability_score": 65.0,
            "suggestions": ["Add AWS experience"],
            "confidence": 0.88,
        }
        assert validate_optimizer_output(content) == []

    def test_missing_keyword_sublists(self):
        content = {
            "keyword_analysis": {},
            "readability_score": 65.0,
            "suggestions": [],
            "confidence": 0.88,
        }
        issues = validate_optimizer_output(content)
        assert any("present" in i for i in issues)
        assert any("missing" in i for i in issues)

    def test_suggestions_wrong_type(self):
        content = {
            "keyword_analysis": {"present": [], "missing": []},
            "readability_score": 65.0,
            "suggestions": "just a string",
            "confidence": 0.88,
        }
        issues = validate_optimizer_output(content)
        assert any("suggestions must be a list" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  FactChecker contract
# ═══════════════════════════════════════════════════════════════════════

class TestFactCheckerContract:
    def test_valid_output(self):
        content = {
            "claims": [
                {"text": "5 years Python", "classification": "verified", "confidence": 0.95},
            ],
            "summary": {"verified": 1, "fabricated": 0},
            "overall_accuracy": 0.95,
            "confidence": 0.93,
        }
        assert validate_fact_checker_output(content) == []

    def test_unknown_classification(self):
        content = {
            "claims": [{"text": "claim", "classification": "maybe_true"}],
            "summary": {"verified": 0, "fabricated": 0},
            "overall_accuracy": 0.5,
            "confidence": 0.5,
        }
        issues = validate_fact_checker_output(content)
        assert any("unknown classification" in i for i in issues)

    def test_missing_summary_counts(self):
        content = {
            "claims": [],
            "summary": {},
            "overall_accuracy": 0.9,
            "confidence": 0.9,
        }
        issues = validate_fact_checker_output(content)
        assert any("verified" in i for i in issues)
        assert any("fabricated" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  Validator contract
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorContract:
    def test_valid_output(self):
        content = {
            "valid": True,
            "checks": {"schema_compliant": True, "format_valid": True},
            "issues": [],
        }
        assert validate_validator_output(content) == []

    def test_missing_checks_keys(self):
        content = {"valid": True, "checks": {}, "issues": []}
        issues = validate_validator_output(content)
        assert any("schema_compliant" in i for i in issues)
        assert any("format_valid" in i for i in issues)

    def test_issue_missing_severity(self):
        content = {
            "valid": False,
            "checks": {"schema_compliant": True, "format_valid": True},
            "issues": [{"description": "bad format"}],
        }
        issues = validate_validator_output(content)
        assert any("severity" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline result contract
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineResultContract:
    def test_valid_result(self):
        assert validate_pipeline_result({"html": "<p>doc</p>"}) == []

    def test_missing_html(self):
        issues = validate_pipeline_result({"text": "no html key"})
        assert any("Missing required keys" in i for i in issues)


# ═══════════════════════════════════════════════════════════════════════
#  Stage dispatcher
# ═══════════════════════════════════════════════════════════════════════

class TestStageDispatcher:
    def test_routes_to_researcher(self):
        issues = validate_stage_output("researcher", {})
        assert len(issues) > 0  # empty dict should fail

    def test_routes_drafter_revision(self):
        # "drafter_revision_1" should resolve to drafter validator
        issues = validate_stage_output("drafter_revision_1", {"html": "<p>ok</p>"})
        assert issues == []

    def test_routes_fact_checker_suffix(self):
        issues = validate_stage_output(
            "fact_checker_final",
            {
                "claims": [],
                "summary": {"verified": 0, "fabricated": 0},
                "overall_accuracy": 1.0,
                "confidence": 0.9,
            },
        )
        assert issues == []

    def test_unknown_stage_returns_empty(self):
        assert validate_stage_output("unknown_agent", {}) == []

    def test_strict_mode_raises(self):
        with pytest.raises(ContractViolation):
            validate_stage_output("researcher", {}, strict=True)


# ═══════════════════════════════════════════════════════════════════════
#  Tool normalizer
# ═══════════════════════════════════════════════════════════════════════

class TestToolNormalizer:
    def test_keyword_overlap_aliases(self):
        raw = {"matches": ["Python"], "gaps": ["AWS"], "extra": 1}
        result = normalize_tool_output("compute_keyword_overlap", raw)
        assert "matched_keywords" in result
        assert "missing_from_document" in result
        assert "matches" not in result
        assert result["extra"] == 1

    def test_readability_aliases(self):
        raw = {"flesch_score": 65.0, "sentences": 10}
        result = normalize_tool_output("compute_readability", raw)
        assert "flesch_reading_ease" in result
        assert "flesch_score" not in result
        assert result["sentences"] == 10

    def test_canonical_key_takes_precedence(self):
        raw = {"flesch_score": 60, "flesch_reading_ease": 65}
        result = normalize_tool_output("compute_readability", raw)
        assert result["flesch_reading_ease"] == 65
        assert "flesch_score" not in result

    def test_unknown_tool_passes_through(self):
        raw = {"key": "value"}
        result = normalize_tool_output("unknown_tool", raw)
        assert result == {"key": "value"}

    def test_non_dict_passes_through(self):
        assert normalize_tool_output("compute_keyword_overlap", "not a dict") == "not a dict"

    def test_normalize_all_tool_results(self):
        tool_results = {
            "compute_keyword_overlap": {"matches": ["a"], "gaps": ["b"]},
            "compute_readability": {"score": 70},
            "other_tool": {"data": 1},
        }
        normalized = normalize_all_tool_results(tool_results)
        assert "matched_keywords" in normalized["compute_keyword_overlap"]
        assert "flesch_reading_ease" in normalized["compute_readability"]
        assert normalized["other_tool"] == {"data": 1}

    def test_does_not_mutate_input(self):
        raw = {"matches": ["Python"], "gaps": ["AWS"]}
        original = dict(raw)
        normalize_tool_output("compute_keyword_overlap", raw)
        assert raw == original
