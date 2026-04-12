# backend/tests/unit/test_agents/test_validator_final_analysis.py
"""Tests for validator consumption of final_analysis data."""
import pytest
from unittest.mock import AsyncMock, patch

from ai_engine.agents.schema_validator import ValidatorAgent


def _make_validator():
    """Create a ValidatorAgent with a mocked AI client."""
    client = AsyncMock()
    client.complete_json = AsyncMock(return_value={
        "confidence": 0.9,
        "issues": [],
    })
    return ValidatorAgent(ai_client=client)


def _good_draft():
    return {"html": "<h1>John Doe</h1><p>Senior Engineer with 10 years experience in Python.</p>" * 5}


def _good_final_analysis():
    return {
        "final_ats_score": 88,
        "initial_ats_score": 70,
        "missing_keywords": ["Docker"],
        "keyword_gap_delta": -3,
        "readability_delta": 5,
        "residual_issue_count": 1,
    }


class TestValidatorFinalAnalysisReviewed:
    """final_analysis_reviewed check should be True when final_analysis is present."""

    @pytest.mark.asyncio
    async def test_final_analysis_reviewed_when_present(self):
        v = _make_validator()
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": _good_final_analysis(),
        }
        result = await v.run(ctx)
        checks = result.content.get("checks", {})
        assert checks.get("final_analysis_reviewed") is True

    @pytest.mark.asyncio
    async def test_final_analysis_reviewed_false_when_absent(self):
        v = _make_validator()
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
        }
        result = await v.run(ctx)
        checks = result.content.get("checks", {})
        assert checks.get("final_analysis_reviewed") is False


class TestValidatorLowATSScore:
    """Validator should flag low final ATS scores on doc-gen pipelines."""

    @pytest.mark.asyncio
    async def test_critically_low_ats_score(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["final_ats_score"] = 45
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        ats_issues = [i for i in issues if "ATS score" in i.get("message", "") and i["severity"] == "high"]
        assert len(ats_issues) >= 1
        assert result.content["checks"]["residual_risk_within_bounds"] is False

    @pytest.mark.asyncio
    async def test_below_target_ats_score(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["final_ats_score"] = 70
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        ats_issues = [i for i in issues if "ATS score" in i.get("message", "")]
        assert len(ats_issues) >= 1
        # Below target but not critical — should be medium severity
        assert any(i["severity"] == "medium" for i in ats_issues)

    @pytest.mark.asyncio
    async def test_good_ats_score_no_issue(self):
        v = _make_validator()
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": _good_final_analysis(),
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        ats_issues = [i for i in issues if "ATS score" in i.get("message", "")]
        assert len(ats_issues) == 0


class TestValidatorMissingKeywords:
    """Validator should flag high missing keyword counts."""

    @pytest.mark.asyncio
    async def test_too_many_missing_keywords(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["missing_keywords"] = ["a", "b", "c", "d", "e", "f"]  # 6 missing
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        kw_issues = [i for i in issues if "keywords still missing" in i.get("message", "")]
        assert len(kw_issues) >= 1
        assert kw_issues[0]["severity"] == "high"
        assert result.content["checks"]["residual_risk_within_bounds"] is False

    @pytest.mark.asyncio
    async def test_moderate_missing_keywords(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["missing_keywords"] = ["x", "y", "z"]  # 3 missing
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        kw_issues = [i for i in issues if "keywords still missing" in i.get("message", "")]
        assert len(kw_issues) >= 1
        assert kw_issues[0]["severity"] == "medium"

    @pytest.mark.asyncio
    async def test_few_missing_keywords_no_issue(self):
        v = _make_validator()
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": _good_final_analysis(),  # has 1 missing keyword
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        kw_issues = [i for i in issues if "keywords still missing" in i.get("message", "")]
        assert len(kw_issues) == 0


class TestValidatorResidualIssues:
    """Validator should flag high residual issue count."""

    @pytest.mark.asyncio
    async def test_high_residual_issues(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["residual_issue_count"] = 8
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        res_issues = [i for i in issues if "residual issue" in i.get("message", "").lower()]
        assert len(res_issues) >= 1
        assert res_issues[0]["severity"] == "high"

    @pytest.mark.asyncio
    async def test_moderate_residual_issues(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["residual_issue_count"] = 3
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        res_issues = [i for i in issues if "residual issue" in i.get("message", "").lower() or "Residual issues" in i.get("message", "")]
        assert len(res_issues) >= 1
        assert res_issues[0]["severity"] == "medium"


class TestValidatorDeltaChecks:
    """Validator should flag worsening keyword gaps and readability drops."""

    @pytest.mark.asyncio
    async def test_keyword_gap_worsened(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["keyword_gap_delta"] = 3  # Gap grew by 3
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        kw_issues = [i for i in issues if "keyword gap worsened" in i.get("message", "").lower()]
        assert len(kw_issues) >= 1
        assert result.content["checks"]["residual_risk_within_bounds"] is False

    @pytest.mark.asyncio
    async def test_readability_dropped(self):
        v = _make_validator()
        fa = _good_final_analysis()
        fa["readability_delta"] = -15  # Significant drop
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        rd_issues = [i for i in issues if "readability" in i.get("message", "").lower()]
        assert len(rd_issues) >= 1

    @pytest.mark.asyncio
    async def test_good_deltas_no_issues(self):
        v = _make_validator()
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": _good_final_analysis(),
        }
        result = await v.run(ctx)
        issues = result.content.get("issues", [])
        delta_issues = [
            i for i in issues
            if "keyword gap" in i.get("message", "").lower()
            or "readability" in i.get("message", "").lower()
        ]
        assert len(delta_issues) == 0


class TestValidatorResidualRiskBounds:
    """The residual_risk_within_bounds check should aggregate properly."""

    @pytest.mark.asyncio
    async def test_all_good_residual_risk_within_bounds(self):
        v = _make_validator()
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": _good_final_analysis(),
        }
        result = await v.run(ctx)
        assert result.content["checks"]["residual_risk_within_bounds"] is True

    @pytest.mark.asyncio
    async def test_bad_final_analysis_residual_risk_out_of_bounds(self):
        v = _make_validator()
        fa = {
            "final_ats_score": 40,
            "missing_keywords": ["a", "b", "c", "d", "e", "f", "g"],
            "keyword_gap_delta": 5,
            "readability_delta": -20,
            "residual_issue_count": 10,
        }
        ctx = {
            "draft": _good_draft(),
            "metadata": {"pipeline": "cv_generation"},
            "citations": [],
            "final_analysis": fa,
        }
        result = await v.run(ctx)
        assert result.content["checks"]["residual_risk_within_bounds"] is False
        assert result.content["checks"]["final_analysis_reviewed"] is True
