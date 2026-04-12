# backend/tests/unit/test_agents/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock, patch
from ai_engine.agents.base import AgentResult
from ai_engine.agents.orchestrator import AgentPipeline, PipelinePolicy, PipelineResult


def _mock_result(content=None, needs_revision=False, flags=None, feedback=None, suggestions=None):
    return AgentResult(
        content=content or {"text": "mock"},
        quality_scores={"impact": 85},
        flags=flags or [],
        latency_ms=1000,
        metadata={"agent": "mock"},
        needs_revision=needs_revision,
        feedback=feedback,
        suggestions=suggestions,
    )


@pytest.fixture
def mock_agents():
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
    optimizer.run_final_analysis = AsyncMock(return_value=_mock_result({
        "initial_ats_score": 70, "final_ats_score": 85,
        "keyword_gap_delta": -3, "readability_delta": 2, "residual_issue_count": 0,
    }))
    optimizer.name = "optimizer"

    fact_checker = AsyncMock()
    fact_checker.run = AsyncMock(return_value=_mock_result(flags=[]))
    fact_checker.name = "fact_checker"

    validator = AsyncMock()
    validator.run = AsyncMock(return_value=_mock_result({"valid": True, "content": {"html": "<p>CV</p>"}}))
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
async def test_pipeline_executes_all_stages(mock_agents):
    pipeline = AgentPipeline(
        name="cv_generation",
        researcher=mock_agents["researcher"],
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        optimizer=mock_agents["optimizer"],
        fact_checker=mock_agents["fact_checker"],
        validator=mock_agents["validator"],
    )
    result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    assert isinstance(result, PipelineResult)
    assert result.content is not None
    assert result.trace_id is not None
    mock_agents["researcher"].run.assert_awaited_once()
    mock_agents["drafter"].run.assert_awaited_once()
    mock_agents["critic"].run.assert_awaited_once()
    mock_agents["validator"].run.assert_awaited_once()
    assert result.content == {"html": "<p>CV</p>"}
    assert result.validation_report == {"valid": True, "content": {"html": "<p>CV</p>"}}


@pytest.mark.asyncio
async def test_pipeline_triggers_revision_when_critic_says_so(mock_agents):
    # First call returns needs_revision=True, second call (re-eval) returns False
    mock_agents["critic"].run = AsyncMock(
        side_effect=[
            _mock_result(
                content={"text": "mock", "confidence": 0.3},
                needs_revision=True, feedback={"issue": "tone"},
            ),
            _mock_result(
                content={"text": "mock", "confidence": 0.95},
                needs_revision=False,
            ),
        ]
    )
    # Use a policy that allows revision when confidence < 0.85
    policy = PipelinePolicy(confidence_threshold=0.85, max_iterations=2)
    pipeline = AgentPipeline(
        name="cv_generation",
        researcher=mock_agents["researcher"],
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        optimizer=mock_agents["optimizer"],
        fact_checker=mock_agents["fact_checker"],
        validator=mock_agents["validator"],
        policy=policy,
    )
    result = await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})
    mock_agents["drafter"].revise.assert_awaited_once()
    assert result.iterations_used == 1


@pytest.mark.asyncio
async def test_pipeline_propagates_pipeline_context_to_critic_and_validator(mock_agents):
    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        validator=mock_agents["validator"],
    )

    await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})

    critic_ctx = mock_agents["critic"].run.await_args.args[0]
    validator_ctx = mock_agents["validator"].run.await_args.args[0]

    assert critic_ctx["original_context"]["pipeline"] == "cv_generation"
    assert validator_ctx["metadata"]["pipeline"] == "cv_generation"


@pytest.mark.asyncio
async def test_revision_receives_full_optimizer_content(mock_agents):
    mock_agents["critic"].run = AsyncMock(
        side_effect=[
            _mock_result(
                content={"text": "mock", "confidence": 0.2},
                needs_revision=True,
                feedback={"critical_issues": []},
            ),
            _mock_result(
                content={"text": "mock", "confidence": 0.95},
                needs_revision=False,
            ),
        ]
    )
    mock_agents["optimizer"].run = AsyncMock(
        return_value=AgentResult(
            content={
                "keyword_analysis": {"missing": ["AWS"]},
                "suggestions": [{"type": "keyword", "priority": "high", "text": "Add AWS in the summary."}],
            },
            quality_scores={},
            flags=[],
            latency_ms=50,
            metadata={"agent": "optimizer"},
            suggestions=[{"type": "keyword", "priority": "high", "text": "Add AWS in the summary."}],
        )
    )

    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        optimizer=mock_agents["optimizer"],
        validator=mock_agents["validator"],
        policy=PipelinePolicy(skip_research=True, skip_fact_check=True, confidence_threshold=0.85),
    )

    await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})

    feedback = mock_agents["drafter"].revise.await_args.kwargs["feedback"]
    assert feedback["optimizer"]["keyword_analysis"]["missing"] == ["AWS"]


@pytest.mark.asyncio
async def test_validator_receives_refreshed_citations_after_revision(mock_agents):
    mock_agents["critic"].run = AsyncMock(
        side_effect=[
            _mock_result(
                content={"text": "mock", "confidence": 0.2},
                needs_revision=True,
                feedback={"critical_issues": []},
            ),
            _mock_result(
                content={"text": "mock", "confidence": 0.95},
                needs_revision=False,
            ),
        ]
    )
    mock_agents["fact_checker"].run = AsyncMock(
        side_effect=[
            AgentResult(
                content={
                    "claims": [
                        {"text": "Old claim", "classification": "fabricated", "confidence": 0.1},
                    ],
                    "summary": {"verified": 0, "fabricated": 1},
                    "overall_accuracy": 0.0,
                    "confidence": 0.1,
                },
                quality_scores={},
                flags=["fabricated: Old claim"],
                latency_ms=20,
                metadata={"agent": "fact_checker"},
            ),
            AgentResult(
                content={
                    "claims": [
                        {
                            "text": "Revised claim",
                            "classification": "verified",
                            "confidence": 0.95,
                            "evidence_sources": ["skill:python"],
                        },
                    ],
                    "summary": {"verified": 1, "fabricated": 0},
                    "overall_accuracy": 1.0,
                    "confidence": 0.95,
                },
                quality_scores={},
                flags=[],
                latency_ms=20,
                metadata={"agent": "fact_checker"},
            ),
        ]
    )
    mock_agents["validator"].run = AsyncMock(
        return_value=AgentResult(
            content={
                "valid": True,
                "checks": {"schema_compliant": True, "format_valid": True},
                "issues": [],
                "content": {"html": "<p>Revised CV</p>"},
            },
            quality_scores={},
            flags=[],
            latency_ms=50,
            metadata={"agent": "validator"},
        )
    )

    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        fact_checker=mock_agents["fact_checker"],
        validator=mock_agents["validator"],
        policy=PipelinePolicy(skip_research=True, confidence_threshold=0.85),
    )

    await pipeline.execute(
        {"user_id": "u1", "user_profile": {"skills": [{"name": "Python"}]}, "job_title": "SWE"}
    )

    assert mock_agents["fact_checker"].run.await_count == 2
    validator_ctx = mock_agents["validator"].run.await_args.args[0]
    assert validator_ctx["citations"][0]["claim_text"] == "Revised claim"
    assert validator_ctx["citations"][0]["evidence_ids"]


@pytest.mark.asyncio
async def test_revision_latency_is_included_in_observability_summary(mock_agents):
    mock_agents["critic"].run = AsyncMock(
        side_effect=[
            _mock_result(
                content={"text": "mock", "confidence": 0.2},
                needs_revision=True,
                feedback={"critical_issues": []},
            ),
            _mock_result(
                content={"text": "mock", "confidence": 0.95},
                needs_revision=False,
            ),
        ]
    )
    mock_agents["validator"].run = AsyncMock(
        return_value=AgentResult(
            content={
                "valid": True,
                "checks": {"schema_compliant": True, "format_valid": True},
                "issues": [],
                "content": {"html": "<p>Revised CV</p>"},
            },
            quality_scores={},
            flags=[],
            latency_ms=30,
            metadata={"agent": "validator"},
        )
    )

    captured = {}

    def _capture_emit(self):
        captured["summary"] = self.build_summary()
        return captured["summary"]

    pipeline = AgentPipeline(
        name="cv_generation",
        drafter=mock_agents["drafter"],
        critic=mock_agents["critic"],
        validator=mock_agents["validator"],
        policy=PipelinePolicy(skip_research=True, skip_fact_check=True, confidence_threshold=0.85),
    )

    with patch("ai_engine.agents.orchestrator.PipelineMetrics.emit", autospec=True, side_effect=_capture_emit):
        await pipeline.execute({"user_id": "u1", "user_profile": {}, "job_title": "SWE"})

    summary = captured["summary"]
    assert "drafter_revision_1" in summary["stage_latencies"]
    assert "critic_re_eval_1" in summary["stage_latencies"]
