"""Runtime contract tests for tool-using agents."""
from unittest.mock import AsyncMock

import pytest

from ai_engine.agents.fact_checker import FactCheckerAgent
from ai_engine.agents.researcher import ResearcherAgent
from ai_engine.agents.tools import AgentTool, ToolRegistry


@pytest.mark.asyncio
async def test_researcher_supplies_document_text_for_overlap_tool():
    captured: dict = {}

    async def overlap_tool(document_text: str, jd_text: str) -> dict:
        captured["document_text"] = document_text
        captured["jd_text"] = jd_text
        return {"match_ratio": 0.5, "matched_keywords": ["python"]}

    tools = ToolRegistry()
    tools.register(
        AgentTool(
            name="compute_keyword_overlap",
            description="Overlap tool",
            parameters={
                "type": "object",
                "properties": {
                    "document_text": {"type": "string"},
                    "jd_text": {"type": "string"},
                },
                "required": ["document_text", "jd_text"],
            },
            fn=overlap_tool,
        )
    )

    ai_client = AsyncMock()
    ai_client.complete_json = AsyncMock(
        side_effect=[
            {
                "reasoning": "Need a quick overlap check against the profile.",
                "next_tool": "compute_keyword_overlap",
                "tool_args": {},
                "done": False,
            },
            {
                "reasoning": "Enough evidence gathered.",
                "done": True,
            },
            {
                "industry": "software",
                "keyword_priority": [],
                "key_signals": ["python"],
                "coverage_score": 0.7,
            },
        ]
    )

    agent = ResearcherAgent(ai_client=ai_client, tools=tools)
    result = await agent.run(
        {
            "job_title": "Software Engineer",
            "jd_text": "Looking for Python and AWS experience.",
            "user_profile": {
                "summary": "Backend engineer with Python systems work.",
                "skills": [{"name": "Python"}, {"name": "FastAPI"}],
                "experience": [{"title": "Engineer", "company": "Acme"}],
            },
        }
    )

    assert captured["jd_text"] == "Looking for Python and AWS experience."
    assert "Python" in captured["document_text"]
    assert result.content["tools_used"] == ["compute_keyword_overlap"]
    assert result.content["tool_steps"] == 1


@pytest.mark.asyncio
async def test_fact_checker_exposes_deterministic_metrics_in_content():
    tools = ToolRegistry()

    async def evidence_tool(user_profile: dict) -> dict:
        return {"skills": ["Python"], "companies": ["Acme"]}

    async def claims_tool(document_text: str) -> dict:
        return {
            "claims": [
                {"text": "Built Python APIs at Acme", "type": "quantified", "position": 0},
            ]
        }

    async def match_tool(claims: list[dict], evidence: dict) -> dict:
        return {
            "matched_claims": [{**claims[0], "sources": ["skill:python", "company:acme"]}],
            "unmatched_claims": [],
            "match_rate": 1.0,
        }

    tools.register(
        AgentTool(
            name="extract_profile_evidence",
            description="Evidence tool",
            parameters={
                "type": "object",
                "properties": {"user_profile": {"type": "object"}},
                "required": ["user_profile"],
            },
            fn=evidence_tool,
        )
    )
    tools.register(
        AgentTool(
            name="extract_claims",
            description="Claims tool",
            parameters={
                "type": "object",
                "properties": {"document_text": {"type": "string"}},
                "required": ["document_text"],
            },
            fn=claims_tool,
        )
    )
    tools.register(
        AgentTool(
            name="match_claims_to_evidence",
            description="Match tool",
            parameters={
                "type": "object",
                "properties": {
                    "claims": {"type": "array"},
                    "evidence": {"type": "object"},
                },
                "required": ["claims", "evidence"],
            },
            fn=match_tool,
        )
    )

    ai_client = AsyncMock()
    ai_client.complete_json = AsyncMock(
        return_value={
            "claims": [{"text": "Built Python APIs at Acme", "classification": "verified", "confidence": 0.95}],
            "summary": {"verified": 1, "enhanced": 0, "fabricated": 0},
            "fabricated_claims": [],
            "overall_accuracy": 1.0,
            "confidence": 0.95,
        }
    )

    agent = FactCheckerAgent(ai_client=ai_client, tools=tools)
    result = await agent.run(
        {
            "draft": {"html": "Built Python APIs at Acme"},
            "source": {"user_profile": {"skills": [{"name": "Python"}], "experience": [{"company": "Acme"}] }},
        }
    )

    assert result.content["deterministic_match_rate"] == 1.0
    assert result.content["total_claims_extracted"] == 1
    assert result.content["tools_used"] == [
        "extract_profile_evidence",
        "extract_claims",
        "match_claims_to_evidence",
    ]
