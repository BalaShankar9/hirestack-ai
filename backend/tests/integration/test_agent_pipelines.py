"""Integration tests for agent pipelines with mock AIClient."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from ai_engine.agents.pipelines import cv_generation_pipeline
from ai_engine.agents.orchestrator import PipelineResult


@pytest.fixture
def mock_ai():
    client = MagicMock()
    client.complete_json = AsyncMock(side_effect=_mock_complete_json)
    client.complete = AsyncMock(return_value="<p>Generated CV HTML</p>")
    client.provider_name = "mock"
    client.model = "mock-model"
    client.max_tokens = 4096
    return client


_call_count = 0


async def _mock_complete_json(prompt: str, **kwargs) -> dict:
    global _call_count
    _call_count += 1
    prompt_lower = prompt.lower()

    if "analyze" in prompt_lower and "job" in prompt_lower:
        return {"industry": "tech", "keyword_priority": [{"keyword": "Python", "priority": "high"}]}
    if "evaluate" in prompt_lower or "quality" in prompt_lower:
        return {"quality_scores": {"impact": 85, "clarity": 90}, "needs_revision": False, "feedback": {}}
    if "optimize" in prompt_lower or "ats" in prompt_lower:
        return {"keyword_analysis": {"present": ["Python"], "missing": []}, "suggestions": []}
    if "verify" in prompt_lower or "claim" in prompt_lower:
        return {"summary": {"verified": 10, "enhanced": 3, "fabricated": 0}, "claims": [], "fabricated_claims": []}
    if "validate" in prompt_lower:
        return {"valid": True, "checks": {}, "issues": []}
    return {"result": "mock"}


@pytest.mark.asyncio
async def test_cv_pipeline_end_to_end(mock_ai):
    global _call_count
    _call_count = 0

    mock_chain = MagicMock()
    mock_chain.generate_tailored_cv = AsyncMock(return_value="<h1>John Doe</h1><p>Software Engineer</p>")

    with patch("ai_engine.agents.pipelines.get_ai_client", return_value=mock_ai):
        with patch("ai_engine.chains.DocumentGeneratorChain", return_value=mock_chain):
            pipeline = cv_generation_pipeline(ai_client=mock_ai)
            result = await pipeline.execute({
                "user_id": "test-user-1",
                "user_profile": {"name": "John", "skills": [{"name": "Python"}]},
                "job_title": "Senior Software Engineer",
                "company": "TestCorp",
                "jd_text": "We need a senior Python developer...",
                "resume_text": "John Doe, 5 years Python experience...",
            })

    assert isinstance(result, PipelineResult)
    assert result.content is not None
    assert result.trace_id is not None
    assert result.total_latency_ms >= 0
    assert _call_count >= 4
