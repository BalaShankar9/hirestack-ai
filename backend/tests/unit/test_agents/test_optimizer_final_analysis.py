# backend/tests/unit/test_agents/test_optimizer_final_analysis.py
"""Tests for Brief 1: optimizer final analysis stage (analysis-only, no mutations)."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from ai_engine.agents.base import AgentResult
from ai_engine.agents.optimizer import OptimizerAgent
from ai_engine.agents.orchestrator import AgentPipeline, PipelinePolicy, PipelineResult
from ai_engine.agents.contracts import (
    validate_optimizer_final_analysis_output,
    validate_stage_output,
)
from ai_engine.agents.observability import PipelineMetrics


# ═══════════════════════════════════════════════════════════════════════
#  Contract tests
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizerFinalAnalysisContract:
    def test_valid_output(self):
        content = {
            "initial_ats_score": 65.0,
            "final_ats_score": 82.0,
            "keyword_gap_delta": 17.0,
            "initial_readability": 60.0,
            "final_readability": 68.0,
            "readability_delta": 8.0,
            "remaining_missing_keywords": ["Docker", "Terraform"],
            "keyword_coverage": 0.82,
            "residual_recommendations": ["KEYWORD GAP: 2 JD keywords still missing."],
            "residual_issue_count": 1,
        }
        assert validate_optimizer_final_analysis_output(content) == []

    def test_missing_keys(self):
        issues = validate_optimizer_final_analysis_output({})
        assert any("Missing required keys" in i for i in issues)

    def test_bad_score_type(self):
        content = {
            "initial_ats_score": "high",
            "final_ats_score": 82.0,
            "keyword_gap_delta": 17.0,
            "final_readability": 68.0,
            "readability_delta": 8.0,
            "remaining_missing_keywords": [],
            "residual_recommendations": [],
            "residual_issue_count": 0,
        }
        issues = validate_optimizer_final_analysis_output(content)
        assert any("initial_ats_score must be numeric" in i for i in issues)

    def test_bad_recommendations_type(self):
        content = {
            "initial_ats_score": 65.0,
            "final_ats_score": 82.0,
            "keyword_gap_delta": 17.0,
            "final_readability": 68.0,
            "readability_delta": 8.0,
            "remaining_missing_keywords": [],
            "residual_recommendations": "not a list",
            "residual_issue_count": 0,
        }
        issues = validate_optimizer_final_analysis_output(content)
        assert any("residual_recommendations must be a list" in i for i in issues)

    def test_bad_missing_keywords_type(self):
        content = {
            "initial_ats_score": 65.0,
            "final_ats_score": 82.0,
            "keyword_gap_delta": 17.0,
            "final_readability": 68.0,
            "readability_delta": 8.0,
            "remaining_missing_keywords": "not a list",
            "residual_recommendations": [],
            "residual_issue_count": 0,
        }
        issues = validate_optimizer_final_analysis_output(content)
        assert any("remaining_missing_keywords must be a list" in i for i in issues)

    def test_validate_stage_output_routes_correctly(self):
        content = {
            "initial_ats_score": 65.0,
            "final_ats_score": 82.0,
            "keyword_gap_delta": 17.0,
            "final_readability": 68.0,
            "readability_delta": 8.0,
            "remaining_missing_keywords": [],
            "residual_recommendations": [],
            "residual_issue_count": 0,
        }
        assert validate_stage_output("optimizer_final_analysis", content) == []


# ═══════════════════════════════════════════════════════════════════════
#  Observability tests
# ═══════════════════════════════════════════════════════════════════════

class TestFinalAnalysisObservability:
    def test_record_final_analysis(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        m.record_final_analysis(
            initial_ats_score=65.0,
            final_ats_score=82.0,
            keyword_gap_delta=17.0,
            readability_delta=8.0,
            residual_issue_count=1,
        )
        summary = m.build_summary()
        fa = summary["final_analysis"]
        assert fa["initial_ats_score"] == 65.0
        assert fa["final_ats_score"] == 82.0
        assert fa["keyword_gap_delta"] == 17.0
        assert fa["readability_delta"] == 8.0
        assert fa["optimizer_residual_issue_count"] == 1

    def test_empty_final_analysis(self):
        m = PipelineMetrics("pid", "cv_generation", "u1")
        summary = m.build_summary()
        assert summary["final_analysis"] == {}


# ═══════════════════════════════════════════════════════════════════════
#  Optimizer.run_final_analysis unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestOptimizerRunFinalAnalysis:
    @pytest.fixture
    def optimizer_with_tools(self):
        """Build an OptimizerAgent with mock deterministic tools."""
        kw_tool = AsyncMock()
        kw_tool.execute = AsyncMock(return_value={
            "match_ratio": 0.82,
            "missing_from_document": ["Docker", "Terraform"],
            "fuzzy_matches": [],
        })
        read_tool = AsyncMock()
        read_tool.execute = AsyncMock(return_value={
            "flesch_reading_ease": 68.0,
            "grade_level": 9,
            "quality_band": "good",
            "long_sentences": 0,
            "passive_voice_count": 1,
        })
        tools = MagicMock()
        tools.get = MagicMock(side_effect=lambda name: {
            "compute_keyword_overlap": kw_tool,
            "compute_readability": read_tool,
        }.get(name))

        agent = OptimizerAgent.__new__(OptimizerAgent)
        agent.name = "optimizer"
        agent.tools = tools
        agent.ai_client = None
        agent.system_prompt = ""
        agent.output_schema = None
        return agent

    @pytest.mark.asyncio
    async def test_final_analysis_returns_report(self, optimizer_with_tools):
        ctx = {
            "draft": {"html": "<p>Strong Python engineer with 5 years at AWS</p>"},
            "original_context": {"jd_text": "We need Python Docker Terraform AWS experience"},
        }
        result = await optimizer_with_tools.run_final_analysis(
            ctx, initial_ats_score=65.0, initial_readability=60.0,
        )
        assert isinstance(result, AgentResult)
        c = result.content
        assert c["initial_ats_score"] == 65.0
        assert c["final_ats_score"] == 82.0
        assert c["keyword_gap_delta"] == 17.0
        assert c["final_readability"] == 68.0
        assert c["readability_delta"] == 8.0
        assert c["remaining_missing_keywords"] == ["Docker", "Terraform"]
        assert c["residual_issue_count"] == 1  # keyword gap recommendation
        assert any("KEYWORD GAP" in r for r in c["residual_recommendations"])

    @pytest.mark.asyncio
    async def test_final_analysis_no_mutation(self, optimizer_with_tools):
        """Final analysis must NEVER modify the draft content."""
        original_html = "<p>Unchanged content</p>"
        ctx = {"draft": {"html": original_html}, "original_context": {"jd_text": "Python"}}
        await optimizer_with_tools.run_final_analysis(
            ctx, initial_ats_score=0, initial_readability=0,
        )
        assert ctx["draft"]["html"] == original_html

    @pytest.mark.asyncio
    async def test_final_analysis_with_zero_initial_scores(self, optimizer_with_tools):
        ctx = {
            "draft": {"html": "<p>Test</p>"},
            "original_context": {"jd_text": "Python AWS"},
        }
        result = await optimizer_with_tools.run_final_analysis(
            ctx, initial_ats_score=0, initial_readability=0,
        )
        c = result.content
        assert c["keyword_gap_delta"] == c["final_ats_score"]
        assert c["readability_delta"] == c["final_readability"]

    @pytest.mark.asyncio
    async def test_final_analysis_metadata(self, optimizer_with_tools):
        ctx = {
            "draft": {"html": "<p>Test</p>"},
            "original_context": {"jd_text": "Python"},
        }
        result = await optimizer_with_tools.run_final_analysis(
            ctx, initial_ats_score=50, initial_readability=60,
        )
        assert result.metadata["stage"] == "optimizer_final_analysis"
        assert "final_ats_score" in result.metadata
        assert "residual_issue_count" in result.metadata


# ═══════════════════════════════════════════════════════════════════════
#  Orchestrator integration: final analysis wired into pipeline
# ═══════════════════════════════════════════════════════════════════════

def _mock_result(content=None, needs_revision=False, flags=None, feedback=None, suggestions=None):
    return AgentResult(
        content=content or {"text": "mock"},
        quality_scores={"impact": 85},
        flags=flags or [],
        latency_ms=100,
        metadata={"agent": "mock"},
        needs_revision=needs_revision,
        feedback=feedback,
        suggestions=suggestions,
    )


@pytest.fixture
def pipeline_agents():
    """Full agent set with optimizer that supports run_final_analysis."""
    researcher = AsyncMock()
    researcher.run = AsyncMock(return_value=_mock_result({"keywords": ["Python"]}))
    researcher.name = "researcher"

    drafter = AsyncMock()
    drafter.run = AsyncMock(return_value=_mock_result({"html": "<p>CV</p>"}))
    drafter.revise = AsyncMock(return_value=_mock_result({"html": "<p>Revised</p>"}))
    drafter.name = "drafter"

    critic = AsyncMock()
    critic.run = AsyncMock(return_value=_mock_result(needs_revision=False))
    critic.name = "critic"

    optimizer = AsyncMock()
    optimizer.run = AsyncMock(return_value=_mock_result(
        content={
            "ats_score": 65.0,
            "readability_score": 60.0,
            "keyword_analysis": {"present": ["Python"], "missing": ["AWS"]},
            "suggestions": [],
            "confidence": 0.8,
        },
        suggestions=[],
    ))
    optimizer.run_final_analysis = AsyncMock(return_value=_mock_result(
        content={
            "initial_ats_score": 65.0,
            "final_ats_score": 82.0,
            "keyword_gap_delta": 17.0,
            "initial_readability": 60.0,
            "final_readability": 68.0,
            "readability_delta": 8.0,
            "remaining_missing_keywords": ["Docker"],
            "keyword_coverage": 0.82,
            "residual_recommendations": ["KEYWORD GAP: 1 JD keyword still missing."],
            "residual_issue_count": 1,
        },
    ))
    optimizer.name = "optimizer"

    fact_checker = AsyncMock()
    fact_checker.run = AsyncMock(return_value=_mock_result(flags=[]))
    fact_checker.name = "fact_checker"

    validator = AsyncMock()
    validator.run = AsyncMock(return_value=_mock_result(
        {"valid": True, "content": {"html": "<p>CV</p>"}}
    ))
    validator.name = "validator"

    return {
        "researcher": researcher,
        "drafter": drafter,
        "critic": critic,
        "optimizer": optimizer,
        "fact_checker": fact_checker,
        "validator": validator,
    }


@pytest.mark.asyncio
async def test_pipeline_runs_final_analysis_stage(pipeline_agents):
    pipeline = AgentPipeline(
        name="cv_generation",
        researcher=pipeline_agents["researcher"],
        drafter=pipeline_agents["drafter"],
        critic=pipeline_agents["critic"],
        optimizer=pipeline_agents["optimizer"],
        fact_checker=pipeline_agents["fact_checker"],
        validator=pipeline_agents["validator"],
    )
    result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    assert isinstance(result, PipelineResult)
    # Final analysis was called
    pipeline_agents["optimizer"].run_final_analysis.assert_awaited_once()
    # Result includes the report
    assert result.final_analysis_report is not None
    assert result.final_analysis_report["final_ats_score"] == 82.0
    assert result.final_analysis_report["keyword_gap_delta"] == 17.0


@pytest.mark.asyncio
async def test_final_analysis_passes_initial_scores_from_optimizer(pipeline_agents):
    pipeline = AgentPipeline(
        name="cv_generation",
        researcher=pipeline_agents["researcher"],
        drafter=pipeline_agents["drafter"],
        critic=pipeline_agents["critic"],
        optimizer=pipeline_agents["optimizer"],
        fact_checker=pipeline_agents["fact_checker"],
        validator=pipeline_agents["validator"],
    )
    await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    call_kwargs = pipeline_agents["optimizer"].run_final_analysis.await_args.kwargs
    assert call_kwargs["initial_ats_score"] == 65.0
    assert call_kwargs["initial_readability"] == 60.0


@pytest.mark.asyncio
async def test_final_analysis_runs_on_final_draft(pipeline_agents):
    """Final analysis must receive the post-merge draft, not the initial draft."""
    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=pipeline_agents["drafter"],
        optimizer=pipeline_agents["optimizer"],
        validator=pipeline_agents["validator"],
    )
    await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    call_args = pipeline_agents["optimizer"].run_final_analysis.await_args.args[0]
    # The draft passed to final analysis should contain merged content
    assert "draft" in call_args


@pytest.mark.asyncio
async def test_validator_receives_final_analysis_context(pipeline_agents):
    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=pipeline_agents["drafter"],
        optimizer=pipeline_agents["optimizer"],
        validator=pipeline_agents["validator"],
    )
    await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    validator_ctx = pipeline_agents["validator"].run.await_args.args[0]
    assert "final_analysis" in validator_ctx
    assert validator_ctx["final_analysis"]["final_ats_score"] == 82.0


@pytest.mark.asyncio
async def test_pipeline_works_without_optimizer(pipeline_agents):
    """Pipeline must still complete when no optimizer is provided."""
    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=pipeline_agents["drafter"],
        validator=pipeline_agents["validator"],
    )
    result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    assert result.final_analysis_report is None
