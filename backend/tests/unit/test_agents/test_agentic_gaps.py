# backend/tests/unit/test_agents/test_agentic_gaps.py
"""
Tests covering the 10 agentic gaps:
  Gap 1: Researcher planning loop (LLM-driven tool selection)
  Gap 2+3: External tools + LLM tool selection infrastructure
  Gap 4: Dynamic pipeline re-routing
  Gap 5: Model router task_type usage
  Gap 6: Worker tasks through pipeline
  Gap 7: Human-in-the-loop gates
  Gap 8: Critic score clamping
  Gap 9: Memory feedback loop
  Gap 10: Distributed lock manager
"""
import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_engine.agents.base import AgentResult
from ai_engine.agents.tools import (
    AgentTool,
    ToolRegistry,
    ToolCall,
    ToolPlan,
    build_researcher_tools,
    _search_company_info,
    _search_salary_data,
    _search_industry_trends,
    _query_user_history,
    _web_search,
)
from ai_engine.agents.orchestrator import (
    AgentPipeline,
    PipelinePolicy,
)
from ai_engine.agents.critic import CriticAgent
from ai_engine.agents.lock import PipelineLockManager


# ═══════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════

def _mock_result(
    content=None, needs_revision=False, flags=None,
    feedback=None, suggestions=None, quality_scores=None,
    latency_ms=100,
):
    return AgentResult(
        content=content or {"text": "mock"},
        quality_scores=quality_scores or {},
        flags=flags or [],
        latency_ms=latency_ms,
        metadata={"agent": "mock"},
        needs_revision=needs_revision,
        feedback=feedback,
        suggestions=suggestions,
    )


def _make_agents(**overrides):
    """Build a full set of mock agents with sensible defaults."""
    researcher = AsyncMock()
    researcher.run = AsyncMock(return_value=_mock_result(
        {"keywords": ["Python"], "tool_results": {}, "coverage_score": 0.8}
    ))
    researcher.name = "researcher"

    drafter = AsyncMock()
    drafter.run = AsyncMock(return_value=_mock_result({"html": "<p>CV</p>"}))
    drafter.revise = AsyncMock(return_value=_mock_result({"html": "<p>Revised CV</p>"}))
    drafter.name = "drafter"

    critic = AsyncMock()
    critic.run = AsyncMock(return_value=_mock_result(
        needs_revision=False,
        quality_scores={"impact": 85, "clarity": 80, "tone_match": 75, "completeness": 90},
    ))
    critic.name = "critic"

    optimizer = AsyncMock()
    optimizer.run = AsyncMock(return_value=_mock_result(suggestions={"keywords": ["AWS"]}))
    optimizer.run_final_analysis = AsyncMock(return_value=_mock_result(
        {"initial_ats_score": 60, "final_ats_score": 80, "keyword_gap_delta": -2,
         "readability_delta": 0.5, "residual_issue_count": 1}
    ))
    optimizer.name = "optimizer"

    fact_checker = AsyncMock()
    fact_checker.run = AsyncMock(return_value=_mock_result(
        {"summary": {"fabricated": 0, "verified": 3}, "claims": []},
        flags=[],
    ))
    fact_checker.name = "fact_checker"

    validator = AsyncMock()
    validator.run = AsyncMock(return_value=_mock_result({"valid": True}))
    validator.name = "validator"

    agents = {
        "researcher": researcher,
        "drafter": drafter,
        "critic": critic,
        "optimizer": optimizer,
        "fact_checker": fact_checker,
        "validator": validator,
    }
    agents.update(overrides)
    return agents


# ═══════════════════════════════════════════════════════════════════════
#  Gap 2+3: External tools + LLM tool selection
# ═══════════════════════════════════════════════════════════════════════

class TestExternalTools:
    """Gap 2: External tool functions exist and handle edge cases."""

    @pytest.mark.asyncio
    async def test_web_search_no_api_key(self):
        """Without API key, returns graceful error, not crash."""
        with patch.dict("os.environ", {}, clear=True):
            result = await _web_search("test query")
            assert result["results"] == []
            assert "error" in result

    @pytest.mark.asyncio
    async def test_search_company_info_short_name(self):
        result = await _search_company_info("")
        assert "error" in result

    @pytest.mark.asyncio
    async def test_search_salary_data_returns_structure(self):
        with patch.dict("os.environ", {}, clear=True):
            result = await _search_salary_data("Software Engineer", "San Francisco")
            assert result["job_title"] == "Software Engineer"
            assert result["location"] == "San Francisco"
            assert isinstance(result["results"], list)

    @pytest.mark.asyncio
    async def test_search_industry_trends_needs_input(self):
        result = await _search_industry_trends()
        assert "error" in result

    @pytest.mark.asyncio
    async def test_query_user_history_no_db(self):
        result = await _query_user_history(user_id="u1", db=None)
        assert "error" in result

    def test_build_researcher_tools_has_external_tools(self):
        """v3 registry includes external tools alongside core tools."""
        reg = build_researcher_tools()
        tool_names = {t.name for t in reg.list_tools()}
        assert "search_company_info" in tool_names
        assert "search_salary_data" in tool_names
        assert "search_industry_trends" in tool_names
        # Core tools still present
        assert "parse_jd" in tool_names
        assert "extract_profile_evidence" in tool_names
        assert "compute_keyword_overlap" in tool_names

    def test_build_researcher_tools_with_db_adds_history(self):
        """When db and user_id provided, query_user_history is available."""
        mock_db = MagicMock()
        reg = build_researcher_tools(db=mock_db, user_id="u123")
        tool_names = {t.name for t in reg.list_tools()}
        assert "query_user_history" in tool_names

    def test_build_researcher_tools_without_db_no_history(self):
        """Without db, query_user_history is NOT registered."""
        reg = build_researcher_tools()
        tool_names = {t.name for t in reg.list_tools()}
        assert "query_user_history" not in tool_names


class TestToolSelectionInfra:
    """Gap 3: LLM-driven tool selection infrastructure."""

    def test_tool_call_dataclass(self):
        tc = ToolCall(tool_name="parse_jd", arguments={"jd_text": "..."})
        assert tc.tool_name == "parse_jd"
        assert tc.reasoning == ""

    def test_tool_plan_defaults(self):
        plan = ToolPlan()
        assert plan.calls == []
        assert plan.done is False
        assert plan.coverage_estimate == 0.0

    @pytest.mark.asyncio
    async def test_select_and_execute_graceful_on_llm_failure(self):
        """If LLM fails, returns a safe ToolPlan with done=True."""
        reg = ToolRegistry()
        reg.register(AgentTool(
            name="test_tool",
            description="test",
            parameters={"type": "object", "properties": {}},
            fn=AsyncMock(return_value={"ok": True}),
        ))

        mock_client = MagicMock()
        mock_client.complete_json = AsyncMock(side_effect=RuntimeError("LLM down"))

        plan = await reg.select_and_execute(
            ai_client=mock_client,
            context="test context",
            working_memory={},
        )
        assert plan.done is True
        assert plan.calls == []

    @pytest.mark.asyncio
    async def test_select_and_execute_parses_llm_response(self):
        """When LLM returns valid JSON, tools are selected correctly."""
        reg = ToolRegistry()
        called = {}

        async def fake_tool(**kwargs):
            called["invoked"] = True
            return {"result": "ok"}

        reg.register(AgentTool(
            name="my_tool",
            description="does stuff",
            parameters={"type": "object", "properties": {}},
            fn=fake_tool,
        ))

        mock_client = MagicMock()
        mock_client.complete_json = AsyncMock(return_value={
            "calls": [{"tool_name": "my_tool", "arguments": {}, "reasoning": "need it"}],
            "done": False,
            "coverage_estimate": 0.6,
            "reasoning": "still gathering",
        })

        plan = await reg.select_and_execute(
            ai_client=mock_client,
            context="test",
            working_memory={},
        )
        assert len(plan.calls) == 1
        assert plan.calls[0].tool_name == "my_tool"
        assert plan.done is False

    @pytest.mark.asyncio
    async def test_select_and_execute_ignores_invalid_tool_names(self):
        """Unknown tool names from LLM are filtered out silently."""
        reg = ToolRegistry()
        mock_client = MagicMock()
        mock_client.complete_json = AsyncMock(return_value={
            "calls": [{"tool_name": "nonexistent_tool", "arguments": {}}],
            "done": False,
            "coverage_estimate": 0.3,
        })

        plan = await reg.select_and_execute(
            ai_client=mock_client, context="", working_memory={},
        )
        assert len(plan.calls) == 0

    def test_describe_for_llm_includes_all_tools(self):
        """describe_for_llm should include external tools."""
        reg = build_researcher_tools()
        desc = reg.describe_for_llm()
        assert "search_company_info" in desc
        assert "parse_jd" in desc


# ═══════════════════════════════════════════════════════════════════════
#  Gap 4: Dynamic pipeline re-routing
# ═══════════════════════════════════════════════════════════════════════

class TestDynamicRerouting:
    """Gap 4: Pipeline re-routes based on intermediate results."""

    @pytest.mark.asyncio
    async def test_skip_revision_when_all_scores_pass(self):
        """When all critic scores exceed threshold, revision is skipped."""
        agents = _make_agents()
        # All scores pass 85% threshold (85 * 100 = 85)
        agents["critic"].run = AsyncMock(return_value=_mock_result(
            needs_revision=True,  # critic says revise, but scores are high
            quality_scores={"impact": 90, "clarity": 88, "tone_match": 92, "completeness": 95},
        ))

        pipeline = AgentPipeline(
            name="cv_generation",
            policy=PipelinePolicy(confidence_threshold=0.85),
            **agents,
        )

        result = await pipeline.execute({"user_profile": {}, "jd_text": "test"})
        # Drafter.revise should NOT have been called
        agents["drafter"].revise.assert_not_called()
        assert result.iterations_used == 0

    @pytest.mark.asyncio
    async def test_reroute_re_research_on_high_fabrication(self):
        """When fact-checker finds ≥5 fabricated claims, researcher re-runs."""
        agents = _make_agents()
        fabricated_claims = [
            {"text": f"claim {i}", "classification": "fabricated", "confidence": 0.9}
            for i in range(6)
        ]
        agents["fact_checker"].run = AsyncMock(return_value=_mock_result(
            {"summary": {"fabricated": 6, "verified": 1}, "claims": fabricated_claims},
            flags=["high_fabrication"],
        ))

        pipeline = AgentPipeline(
            name="cv_generation",
            **agents,
        )

        result = await pipeline.execute({"user_profile": {}, "jd_text": "test"})
        # Researcher should have been called twice (initial + reroute)
        assert agents["researcher"].run.call_count == 2
        # Drafter should have been called twice (initial + reroute re-draft)
        assert agents["drafter"].run.call_count == 2


# ═══════════════════════════════════════════════════════════════════════
#  Gap 5: Model router for agents
# ═══════════════════════════════════════════════════════════════════════

class TestModelRouterAgents:
    """Gap 5: Agents pass task_type to the AI client."""

    def test_model_router_has_task_types(self):
        from ai_engine.model_router import _DEFAULT_ROUTES
        assert "research" in _DEFAULT_ROUTES
        assert "critique" in _DEFAULT_ROUTES
        assert "optimization" in _DEFAULT_ROUTES
        assert "validation" in _DEFAULT_ROUTES
        assert "fact_checking" in _DEFAULT_ROUTES
        assert "drafting" in _DEFAULT_ROUTES

    def test_model_router_returns_model_for_task(self):
        from ai_engine.model_router import resolve_model
        model = resolve_model("research", "fallback")
        assert model  # not None or empty
        assert isinstance(model, str)
        assert model != "fallback"  # should resolve to a real model

    def test_model_router_different_models_for_heavy_vs_light(self):
        from ai_engine.model_router import resolve_model
        research_model = resolve_model("research", "fallback")
        validation_model = resolve_model("validation", "fallback")
        # Research should use the heavier model, validation the lighter one
        assert "pro" in research_model or research_model != validation_model


# ═══════════════════════════════════════════════════════════════════════
#  Gap 6: Worker tasks through pipeline
# ═══════════════════════════════════════════════════════════════════════

class TestWorkerPipelineIntegration:
    """Gap 6: Worker tasks use AgentPipeline, not raw chains."""

    def test_build_pipeline_factory_exists(self):
        from ai_engine.agents.pipelines import build_pipeline
        assert callable(build_pipeline)

    def test_build_pipeline_unknown_name_raises(self):
        from ai_engine.agents.pipelines import build_pipeline
        with pytest.raises(KeyError, match="Unknown pipeline"):
            build_pipeline("nonexistent_pipeline_xyz")

    def test_build_pipeline_cv_generation(self):
        """build_pipeline('cv_generation') returns a configured pipeline."""
        from ai_engine.agents.pipelines import build_pipeline
        pipeline = build_pipeline("cv_generation")
        assert isinstance(pipeline, AgentPipeline)
        assert pipeline.name == "cv_generation"
        assert pipeline.researcher is not None
        assert pipeline.drafter is not None
        assert pipeline.critic is not None

    def test_build_pipeline_cover_letter(self):
        from ai_engine.agents.pipelines import build_pipeline
        pipeline = build_pipeline("cover_letter")
        assert pipeline.name == "cover_letter"

    def test_worker_document_task_attempts_pipeline(self):
        """The worker task code references build_pipeline (import check)."""
        # This is a static analysis test — verify the code path exists
        import ast
        import pathlib
        src = pathlib.Path(__file__).resolve().parents[4] / "workers" / "tasks" / "document_tasks.py"
        tree = ast.parse(src.read_text())
        source_code = src.read_text()
        assert "build_pipeline" in source_code or "pipeline" in source_code.lower()


# ═══════════════════════════════════════════════════════════════════════
#  Gap 7: Human-in-the-loop gates
# ═══════════════════════════════════════════════════════════════════════

class TestHumanInTheLoop:
    """Gap 7: Pipeline supports human approval gates."""

    def test_policy_has_approval_field(self):
        p = PipelinePolicy()
        assert hasattr(p, "require_human_approval_after")
        assert p.require_human_approval_after == ()

    def test_policy_approval_configurable(self):
        p = PipelinePolicy(require_human_approval_after=("drafter", "critic"))
        assert "drafter" in p.require_human_approval_after
        assert "critic" in p.require_human_approval_after

    @pytest.mark.asyncio
    async def test_pipeline_has_approval_callback(self):
        """Pipeline accepts on_approval_request callback."""
        agents = _make_agents()
        callback = AsyncMock(return_value=True)
        pipeline = AgentPipeline(
            name="cv_generation",
            on_approval_request=callback,
            **agents,
        )
        assert pipeline.on_approval_request is callback

    @pytest.mark.asyncio
    async def test_pipeline_calls_approval_after_drafter(self):
        """When policy requires approval after drafter, callback is invoked."""
        agents = _make_agents()
        callback = AsyncMock(return_value=True)

        pipeline = AgentPipeline(
            name="cv_generation",
            on_approval_request=callback,
            policy=PipelinePolicy(require_human_approval_after=("drafter",)),
            **agents,
        )

        result = await pipeline.execute({"user_profile": {}, "jd_text": "test"})
        callback.assert_called_once()
        call_arg = callback.call_args[0][0]
        assert call_arg["stage"] == "drafter"
        assert "result_summary" in call_arg

    @pytest.mark.asyncio
    async def test_pipeline_aborts_on_rejection(self):
        """When approval callback returns False, pipeline returns early."""
        agents = _make_agents()
        callback = AsyncMock(return_value=False)

        pipeline = AgentPipeline(
            name="cv_generation",
            on_approval_request=callback,
            policy=PipelinePolicy(require_human_approval_after=("drafter",)),
            **agents,
        )

        result = await pipeline.execute({"user_profile": {}, "jd_text": "test"})
        # Pipeline should abort — critic should NOT be called
        agents["critic"].run.assert_not_called()
        assert result.validation_report == {"status": "aborted", "reason": "Human review rejected after drafter"}

    @pytest.mark.asyncio
    async def test_pipeline_auto_approves_without_callback(self):
        """Without an approval callback, stages requiring approval auto-approve."""
        agents = _make_agents()

        pipeline = AgentPipeline(
            name="cv_generation",
            # No on_approval_request callback
            policy=PipelinePolicy(require_human_approval_after=("drafter",)),
            **agents,
        )

        # Should complete without error
        result = await pipeline.execute({"user_profile": {}, "jd_text": "test"})
        assert result.content is not None


# ═══════════════════════════════════════════════════════════════════════
#  Gap 8: Critic score clamping
# ═══════════════════════════════════════════════════════════════════════

class TestCriticScoreClamping:
    """Gap 8: Critic scores are validated and clamped to 0-100."""

    @pytest.mark.asyncio
    async def test_clamp_scores_above_100(self):
        """Scores > 100 should be clamped to 100."""
        client = MagicMock()
        client.complete_json = AsyncMock(return_value={
            "quality_scores": {
                "impact": 150,
                "clarity": 200,
                "tone_match": 100,
                "completeness": 95,
            },
            "confidence": 0.8,
            "suggestions": [],
            "overall_assessment": "good",
        })

        critic = CriticAgent(ai_client=client)
        result = await critic.run({"draft": {"text": "hello"}, "original_context": {}})
        qs = result.quality_scores
        assert qs["impact"] <= 100
        assert qs["clarity"] <= 100

    @pytest.mark.asyncio
    async def test_clamp_negative_scores(self):
        """Negative scores should be clamped to 0."""
        client = MagicMock()
        client.complete_json = AsyncMock(return_value={
            "quality_scores": {
                "impact": -10,
                "clarity": -5,
                "tone_match": 0,
                "completeness": 50,
            },
            "confidence": 0.5,
            "suggestions": [],
            "overall_assessment": "poor",
        })

        critic = CriticAgent(ai_client=client)
        result = await critic.run({"draft": {"text": "hello"}, "original_context": {}})
        qs = result.quality_scores
        assert qs["impact"] >= 0
        assert qs["clarity"] >= 0

    @pytest.mark.asyncio
    async def test_clamp_non_numeric_defaults_to_zero(self):
        """Non-numeric scores should default to 0."""
        client = MagicMock()
        client.complete_json = AsyncMock(return_value={
            "quality_scores": {
                "impact": "high",
                "clarity": None,
                "tone_match": 75,
                "completeness": 80,
            },
            "confidence": 0.6,
            "suggestions": [],
            "overall_assessment": "ok",
        })

        critic = CriticAgent(ai_client=client)
        result = await critic.run({"draft": {"text": "hello"}, "original_context": {}})
        qs = result.quality_scores
        assert qs["impact"] == 0
        assert qs["clarity"] == 0
        assert qs["tone_match"] == 75
        assert qs["completeness"] == 80


# ═══════════════════════════════════════════════════════════════════════
#  Gap 9: Memory feedback loop
# ═══════════════════════════════════════════════════════════════════════

class TestMemoryFeedback:
    """Gap 9: Pipeline rates recalled memories based on outcome quality."""

    @pytest.mark.asyncio
    async def test_memory_feedback_called_on_high_quality(self):
        """When quality scores are high, recalled memories are rated useful."""
        agents = _make_agents()
        agents["critic"].run = AsyncMock(return_value=_mock_result(
            quality_scores={"impact": 90, "clarity": 85, "tone_match": 80, "completeness": 88},
        ))

        mock_memory = MagicMock()
        mock_memory.arecall = AsyncMock(return_value=[
            {"id": "mem1", "content": "prefer concise language"},
            {"id": "mem2", "content": "focus on impact"},
        ])
        mock_memory.astore = AsyncMock()
        mock_memory.afeedback = AsyncMock()

        pipeline = AgentPipeline(name="cv_generation", **agents)
        pipeline.memory = mock_memory

        result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "jd_text": "test"})

        # afeedback should be called for each recalled memory
        assert mock_memory.afeedback.call_count == 2
        # With avg ~85.75, should be useful (>= 70)
        mock_memory.afeedback.assert_any_call("mem1", True)
        mock_memory.afeedback.assert_any_call("mem2", True)

    @pytest.mark.asyncio
    async def test_memory_feedback_not_useful_on_low_quality(self):
        """When quality scores are low, recalled memories are rated not useful."""
        agents = _make_agents()
        agents["critic"].run = AsyncMock(return_value=_mock_result(
            quality_scores={"impact": 40, "clarity": 50, "tone_match": 30, "completeness": 45},
        ))

        mock_memory = MagicMock()
        mock_memory.arecall = AsyncMock(return_value=[
            {"id": "mem1", "content": "some old advice"},
        ])
        mock_memory.astore = AsyncMock()
        mock_memory.afeedback = AsyncMock()

        pipeline = AgentPipeline(name="cv_generation", **agents)
        pipeline.memory = mock_memory

        result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "jd_text": "test"})

        # With avg ~41.25, should NOT be useful (< 70)
        mock_memory.afeedback.assert_called_once_with("mem1", False)


# ═══════════════════════════════════════════════════════════════════════
#  Gap 10: Distributed lock manager
# ═══════════════════════════════════════════════════════════════════════

class TestDistributedLock:
    """Gap 10: Lock manager supports both in-memory and DB-based modes."""

    @pytest.mark.asyncio
    async def test_in_memory_lock_acquires(self):
        mgr = PipelineLockManager()
        async with mgr.acquire("user1", "cv_gen", "p1"):
            pass

    @pytest.mark.asyncio
    async def test_in_memory_lock_blocks_concurrent(self):
        mgr = PipelineLockManager()
        order = []

        async def first():
            async with mgr.acquire("u1", "cv", "p1"):
                order.append("first_start")
                await asyncio.sleep(0.05)
                order.append("first_end")

        async def second():
            await asyncio.sleep(0.01)
            async with mgr.acquire("u1", "cv", "p2"):
                order.append("second_start")

        await asyncio.gather(first(), second())
        assert order == ["first_start", "first_end", "second_start"]

    @pytest.mark.asyncio
    async def test_lock_allows_different_pipelines(self):
        mgr = PipelineLockManager()
        order = []

        async def pipe1():
            async with mgr.acquire("u1", "cv", "p1"):
                order.append("cv")
                await asyncio.sleep(0.02)

        async def pipe2():
            async with mgr.acquire("u1", "cover_letter", "p2"):
                order.append("cl")
                await asyncio.sleep(0.02)

        await asyncio.gather(pipe1(), pipe2())
        assert "cv" in order and "cl" in order

    def test_lock_supports_db_parameter(self):
        """Lock manager accepts a db parameter for distributed mode."""
        mgr = PipelineLockManager(db=MagicMock())
        assert mgr._db is not None

    @pytest.mark.asyncio
    async def test_lock_timeout_in_memory(self):
        mgr = PipelineLockManager(timeout_seconds=0.1)
        async with mgr.acquire("u1", "cv", "p1"):
            with pytest.raises(asyncio.TimeoutError):
                async with mgr.acquire("u1", "cv", "p2"):
                    pass


# ═══════════════════════════════════════════════════════════════════════
#  Gap 1: Researcher planning loop
# ═══════════════════════════════════════════════════════════════════════

class TestResearcherPlanningLoop:
    """Gap 1: Researcher has LLM-driven planning loop after core tools."""

    def test_researcher_has_planning_constants(self):
        from ai_engine.agents.researcher import ResearcherAgent
        agent = ResearcherAgent()
        assert hasattr(agent, "MAX_TOOL_STEPS")
        assert hasattr(agent, "COVERAGE_THRESHOLD")
        assert agent.MAX_TOOL_STEPS >= 3
        assert 0 < agent.COVERAGE_THRESHOLD <= 1.0

    def test_researcher_imports_tool_plan(self):
        """Researcher imports ToolPlan for planning loop integration."""
        from ai_engine.agents.researcher import ToolPlan
        plan = ToolPlan(done=True)
        assert plan.done is True

    @pytest.mark.asyncio
    async def test_researcher_runs_planning_loop(self):
        """Researcher calls select_and_execute after core tools."""
        from ai_engine.agents.researcher import ResearcherAgent

        mock_client = MagicMock()
        # First call: synthesis (core tools phase doesn't call LLM)
        # The planning loop calls select_and_execute on the registry
        mock_client.complete_json = AsyncMock(side_effect=[
            # Planning loop LLM response (says done)
            {"calls": [], "done": True, "coverage_estimate": 0.9, "reasoning": "sufficient"},
            # Synthesis LLM response
            {
                "coverage_score": 0.85,
                "company_context": "Tech company",
                "key_requirements": ["Python", "AWS"],
                "user_strengths": ["Backend dev"],
                "gaps": [],
                "tone_guidance": "Professional",
            },
        ])

        researcher = ResearcherAgent(ai_client=mock_client)
        result = await researcher.run({
            "jd_text": "Python engineer with AWS",
            "job_title": "Software Engineer",
            "company": "TestCo",
            "user_profile": {"skills": [{"name": "Python"}]},
        })

        assert result.content is not None
        # LLM should have been called at least twice (planning + synthesis)
        assert mock_client.complete_json.call_count >= 2
