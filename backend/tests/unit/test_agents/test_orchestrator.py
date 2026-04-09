# backend/tests/unit/test_agents/test_orchestrator.py
import pytest
from unittest.mock import AsyncMock
from ai_engine.agents.base import AgentResult
from ai_engine.agents.orchestrator import AgentPipeline, PipelineResult


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


@pytest.mark.asyncio
async def test_pipeline_triggers_revision_when_critic_says_so(mock_agents):
    mock_agents["critic"].run = AsyncMock(
        return_value=_mock_result(needs_revision=True, feedback={"issue": "tone"})
    )
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
    mock_agents["drafter"].revise.assert_awaited_once()
    assert result.iterations_used == 1
