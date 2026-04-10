# backend/tests/unit/test_agents/test_schemas.py
"""Tests for per-agent output schemas."""
import pytest
from ai_engine.agents.schemas import (
    RESEARCHER_SCHEMA,
    CRITIC_SCHEMA,
    OPTIMIZER_SCHEMA,
    FACT_CHECKER_SCHEMA,
    VALIDATOR_SCHEMA,
)


@pytest.mark.parametrize("schema,name,required_keys", [
    (RESEARCHER_SCHEMA, "researcher", {"industry", "keyword_priority", "key_signals", "coverage_score"}),
    (CRITIC_SCHEMA, "critic", {"quality_scores", "needs_revision", "feedback", "confidence"}),
    (OPTIMIZER_SCHEMA, "optimizer", {"keyword_analysis", "readability_score", "suggestions", "confidence"}),
    (FACT_CHECKER_SCHEMA, "fact_checker", {"claims", "summary", "fabricated_claims", "overall_accuracy", "confidence"}),
    (VALIDATOR_SCHEMA, "validator", {"valid", "checks", "issues", "confidence"}),
])
def test_schema_has_required_fields(schema, name, required_keys):
    assert "type" in schema, f"{name} schema missing 'type'"
    assert schema["type"] == "object"
    props = schema.get("properties", {})
    assert required_keys <= set(props.keys()), (
        f"{name} schema missing keys: {required_keys - set(props.keys())}"
    )
    req = set(schema.get("required", []))
    assert required_keys <= req, (
        f"{name} schema missing required: {required_keys - req}"
    )


@pytest.mark.parametrize("schema", [
    RESEARCHER_SCHEMA,
    CRITIC_SCHEMA,
    OPTIMIZER_SCHEMA,
    FACT_CHECKER_SCHEMA,
    VALIDATOR_SCHEMA,
])
def test_schema_has_confidence(schema):
    """Every schema that supplies confidence must type it as a number."""
    props = schema.get("properties", {})
    if "confidence" in props:
        assert props["confidence"]["type"] == "number"
