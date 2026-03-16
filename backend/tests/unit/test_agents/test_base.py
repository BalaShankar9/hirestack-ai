import pytest
from ai_engine.agents.base import AgentResult, BaseAgent


def test_agent_result_creation():
    result = AgentResult(
        content={"text": "hello"},
        quality_scores={"impact": 85},
        flags=[],
        latency_ms=1200,
        metadata={"agent": "critic"},
    )
    assert result.content == {"text": "hello"}
    assert result.quality_scores["impact"] == 85
    assert result.latency_ms == 1200
    assert result.flags == []


def test_agent_result_needs_revision_false_by_default():
    result = AgentResult(
        content={}, quality_scores={}, flags=[], latency_ms=0, metadata={},
    )
    assert result.needs_revision is False


def test_agent_result_needs_revision_true():
    result = AgentResult(
        content={}, quality_scores={}, flags=[], latency_ms=0, metadata={},
        needs_revision=True,
        feedback={"issue": "tone mismatch"},
    )
    assert result.needs_revision is True
    assert result.feedback == {"issue": "tone mismatch"}


def test_base_agent_is_abstract():
    with pytest.raises(TypeError):
        BaseAgent(name="test", system_prompt="test", output_schema={})
