# backend/tests/unit/test_agents/test_orchestrator_policy.py
"""Tests for the policy-driven orchestrator behavior."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_engine.agents.base import AgentResult
from ai_engine.agents.orchestrator import (
    AgentPipeline,
    PipelinePolicy,
    PipelineResult,
    DEFAULT_POLICIES,
    POLICY_FULL,
    POLICY_LIGHT,
    POLICY_STRICT,
    _merge_optimizations,
)


def _mock_result(
    content=None, needs_revision=False, flags=None,
    feedback=None, suggestions=None, quality_scores=None,
):
    return AgentResult(
        content=content or {"text": "mock"},
        quality_scores=quality_scores or {"impact": 85},
        flags=flags or [],
        latency_ms=100,
        metadata={"agent": "mock"},
        needs_revision=needs_revision,
        feedback=feedback,
        suggestions=suggestions,
    )


def _make_agents():
    """Build a full set of mock agents."""
    researcher = AsyncMock()
    researcher.run = AsyncMock(return_value=_mock_result({"keywords": ["Python"]}))
    researcher.name = "researcher"

    drafter = AsyncMock()
    drafter.run = AsyncMock(return_value=_mock_result({"html": "<p>CV</p>"}))
    drafter.revise = AsyncMock(return_value=_mock_result({"html": "<p>Revised CV</p>"}))
    drafter.name = "drafter"

    critic = AsyncMock()
    critic.run = AsyncMock(return_value=_mock_result(needs_revision=False))
    critic.name = "critic"

    optimizer = AsyncMock()
    optimizer.run = AsyncMock(return_value=_mock_result(suggestions={"keywords": ["AWS"]}))
    optimizer.name = "optimizer"

    fact_checker = AsyncMock()
    fact_checker.run = AsyncMock(return_value=_mock_result(flags=[]))
    fact_checker.name = "fact_checker"

    validator = AsyncMock()
    validator.run = AsyncMock(return_value=_mock_result({"valid": True}))
    validator.name = "validator"

    return {
        "researcher": researcher,
        "drafter": drafter,
        "critic": critic,
        "optimizer": optimizer,
        "fact_checker": fact_checker,
        "validator": validator,
    }


# ═══════════════════════════════════════════════════════════════════════
#  PipelinePolicy unit tests
# ═══════════════════════════════════════════════════════════════════════

class TestPipelinePolicy:
    def test_should_research_default(self):
        p = PipelinePolicy()
        assert p.should_research("cv_generation", {}) is True
        # Low-risk skips research
        assert p.should_research("learning", {}) is False
        assert p.should_research("salary_coach", {}) is False

    def test_should_research_skip_override(self):
        p = PipelinePolicy(skip_research=True)
        assert p.should_research("cv_generation", {}) is False

    def test_should_critique_default(self):
        p = PipelinePolicy()
        assert p.should_critique("cv_generation") is True
        assert p.should_critique("resume_parse") is False  # skipped for parse

    def test_should_critique_skip_override(self):
        p = PipelinePolicy(skip_critique=True)
        assert p.should_critique("cv_generation") is False

    def test_should_fact_check_always_for_doc_gen(self):
        p = PipelinePolicy()
        assert p.should_fact_check("cv_generation", {}) is True
        assert p.should_fact_check("cover_letter", {}) is True
        assert p.should_fact_check("portfolio", {}) is True

    def test_should_fact_check_skip_override(self):
        p = PipelinePolicy(skip_fact_check=True)
        assert p.should_fact_check("cv_generation", {}) is False

    def test_should_fact_check_claim_threshold(self):
        p = PipelinePolicy(claim_threshold=2)
        # Content with numbers triggers fact-check
        content = {"text": "Led 5 people", "summary": "Saved $1M"}
        assert p.should_fact_check("benchmark", content) is True
        # Content without numbers doesn't
        assert p.should_fact_check("benchmark", {"text": "No claims"}) is False

    def test_should_revise(self):
        p = PipelinePolicy(confidence_threshold=0.85)
        assert p.should_revise(0.5) is True  # low confidence → revise
        assert p.should_revise(0.85) is False  # meets threshold
        assert p.should_revise(0.95) is False  # above threshold

    def test_effective_max_iterations_default(self):
        p = PipelinePolicy()
        assert p.effective_max_iterations(2) == 2

    def test_effective_max_iterations_override(self):
        p = PipelinePolicy(max_iterations=5)
        assert p.effective_max_iterations(2) == 5


class TestDefaultPolicies:
    def test_all_pipeline_names_have_policies(self):
        expected = {
            "resume_parse", "benchmark", "gap_analysis", "cv_generation",
            "cover_letter", "personal_statement", "portfolio", "ats_scanner",
            "interview", "career_roadmap", "ab_lab", "salary_coach", "learning",
        }
        assert expected <= set(DEFAULT_POLICIES.keys())

    def test_strict_policy(self):
        assert POLICY_STRICT.confidence_threshold == 0.95
        assert POLICY_STRICT.max_iterations == 3

    def test_light_policy(self):
        assert POLICY_LIGHT.skip_research is True
        assert POLICY_LIGHT.skip_fact_check is True
        assert POLICY_LIGHT.max_iterations == 1


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline execution tests
# ═══════════════════════════════════════════════════════════════════════

class TestPipelineExecution:
    @pytest.mark.asyncio
    async def test_skip_research_skips_researcher(self):
        agents = _make_agents()
        policy = PipelinePolicy(skip_research=True)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            researcher=agents["researcher"],
            drafter=agents["drafter"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        agents["researcher"].run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_critique_skips_critic(self):
        agents = _make_agents()
        policy = PipelinePolicy(skip_critique=True, skip_fact_check=True)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            critic=agents["critic"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        agents["critic"].run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skip_fact_check(self):
        agents = _make_agents()
        policy = PipelinePolicy(skip_fact_check=True)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            fact_checker=agents["fact_checker"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        agents["fact_checker"].run.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_max_iterations_caps_revisions(self):
        agents = _make_agents()
        # Critic always says revise
        agents["critic"].run = AsyncMock(
            return_value=_mock_result(
                content={"confidence": 0.1},
                needs_revision=True,
                feedback={"issue": "bad"},
            )
        )
        policy = PipelinePolicy(confidence_threshold=0.9, max_iterations=2)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            critic=agents["critic"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        assert result.iterations_used == 2
        assert agents["drafter"].revise.await_count == 2

    @pytest.mark.asyncio
    async def test_no_revision_when_confidence_high(self):
        agents = _make_agents()
        agents["critic"].run = AsyncMock(
            return_value=_mock_result(
                content={"confidence": 0.95},
                needs_revision=True,  # critic says revise, but confidence is high
            )
        )
        policy = PipelinePolicy(confidence_threshold=0.9)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            critic=agents["critic"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        # Policy overrides: confidence 0.95 >= threshold 0.9 → no revision
        assert result.iterations_used == 0
        agents["drafter"].revise.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_revision_stops_early_when_confidence_improves(self):
        agents = _make_agents()
        agents["critic"].run = AsyncMock(
            side_effect=[
                # Initial run: low confidence
                _mock_result(content={"confidence": 0.3}, needs_revision=True, feedback={"issue": "x"}),
                # After first revision re-eval: high confidence
                _mock_result(content={"confidence": 0.95}, needs_revision=False),
            ]
        )
        policy = PipelinePolicy(confidence_threshold=0.85, max_iterations=5)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            critic=agents["critic"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        # Should stop after 1 revision, not use all 5
        assert result.iterations_used == 1
        agents["drafter"].revise.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pipeline_result_has_trace_id(self):
        agents = _make_agents()
        pipeline = AgentPipeline(
            name="ats_scanner",
            drafter=agents["drafter"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        assert isinstance(result.trace_id, str)
        assert len(result.trace_id) > 0

    @pytest.mark.asyncio
    async def test_sse_callback_invoked(self):
        agents = _make_agents()
        events = []

        async def mock_sse(payload):
            events.append(payload)

        policy = PipelinePolicy(skip_research=True, skip_critique=True, skip_fact_check=True)
        pipeline = AgentPipeline(
            name="test_pipe", policy=policy,
            drafter=agents["drafter"],
            validator=agents["validator"],
            on_stage_update=mock_sse,
        )
        await pipeline.execute({"user_id": "u1"})
        # Should have drafter running+completed and validator running+completed
        stages = [e["stage"] for e in events]
        assert "drafter" in stages
        assert "validator" in stages

    @pytest.mark.asyncio
    async def test_memory_recall_wired(self):
        """Memory recall is called when memory is present."""
        agents = _make_agents()
        mock_memory = AsyncMock()
        mock_memory.arecall = AsyncMock(return_value=[{"key": "val"}])
        mock_memory.astore = AsyncMock()

        policy = PipelinePolicy(skip_research=True, skip_critique=True, skip_fact_check=True)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            validator=agents["validator"],
        )
        pipeline.memory = mock_memory
        await pipeline.execute({"user_id": "u1"})
        mock_memory.arecall.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_memory_writeback_wired(self):
        """Memory writeback stores pipeline results."""
        agents = _make_agents()
        mock_memory = AsyncMock()
        mock_memory.arecall = AsyncMock(return_value=[])
        mock_memory.astore = AsyncMock()

        policy = PipelinePolicy(skip_research=True, skip_critique=True, skip_fact_check=True)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            validator=agents["validator"],
        )
        pipeline.memory = mock_memory
        await pipeline.execute({"user_id": "u1"})
        mock_memory.astore.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_parallel_agent_failure_doesnt_crash(self):
        """If one parallel agent fails, pipeline still completes."""
        agents = _make_agents()
        agents["optimizer"].run = AsyncMock(side_effect=RuntimeError("boom"))
        policy = PipelinePolicy(skip_fact_check=True)
        pipeline = AgentPipeline(
            name="cv_generation", policy=policy,
            drafter=agents["drafter"],
            critic=agents["critic"],
            optimizer=agents["optimizer"],
            validator=agents["validator"],
        )
        result = await pipeline.execute({"user_id": "u1"})
        # Should still produce a result
        assert isinstance(result, PipelineResult)
        # Optimizer report should be empty since it failed
        assert result.optimization_report == {}


# ═══════════════════════════════════════════════════════════════════════
#  Merge optimizations tests
# ═══════════════════════════════════════════════════════════════════════

class TestMergeOptimizations:
    def test_basic_merge(self):
        draft = {"html": "<p>Hello</p>"}
        opt = {"keyword_analysis": {"matched": ["Python"]}, "suggestions": ["add AWS"]}
        fc = {"summary": {"total": 1, "verified": 1}, "claims": []}
        result = _merge_optimizations(draft, opt, fc)
        assert "_optimization_report" in result
        assert "_fact_check_report" in result
        assert result["html"] == "<p>Hello</p>"

    def test_fabricated_claims_removed_from_html(self):
        draft = {"html": "Led a team of 500. Built systems."}
        opt = {}
        fc = {"fabricated_claims": [{"text": "Led a team of 500"}], "summary": {}}
        result = _merge_optimizations(draft, opt, fc)
        assert "Led a team of 500" not in result["html"]
        assert "Built systems." in result["html"]

    def test_does_not_mutate_inputs(self):
        draft = {"html": "<p>test</p>"}
        opt = {"suggestions": []}
        fc = {}
        result = _merge_optimizations(draft, opt, fc)
        assert "_optimization_report" not in draft
