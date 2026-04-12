# backend/tests/unit/test_agents/test_tools.py
"""Tests for the agent tool registry and deterministic tools."""
import pytest
from ai_engine.agents.tools import (
    AgentTool,
    ToolRegistry,
    build_researcher_tools,
    build_fact_checker_tools,
    build_optimizer_tools,
    _parse_jd,
    _extract_profile_evidence,
    _compute_keyword_overlap,
    _compute_readability,
    _extract_claims,
    _match_claims_to_evidence,
)


# ── Tool Registry ─────────────────────────────────────────────────────

def test_registry_register_and_get():
    reg = ToolRegistry()
    tool = AgentTool(
        name="test_tool",
        description="A test tool",
        parameters={"type": "object", "properties": {}},
        fn=lambda: {},
    )
    reg.register(tool)
    assert reg.get("test_tool") is tool
    assert reg.get("nonexistent") is None


def test_registry_list_tools():
    reg = build_researcher_tools()
    tools = reg.list_tools()
    assert len(tools) >= 3  # 3 core + external tools
    names = {t.name for t in tools}
    assert "parse_jd" in names
    assert "extract_profile_evidence" in names
    assert "compute_keyword_overlap" in names


def test_registry_describe_for_llm():
    reg = build_researcher_tools()
    desc = reg.describe_for_llm()
    assert "parse_jd" in desc
    assert "extract_profile_evidence" in desc


def test_registry_describe_as_json():
    reg = build_researcher_tools()
    desc = reg.describe_as_json()
    assert len(desc) >= 3  # 3 core + external tools
    assert all("name" in d and "description" in d for d in desc)


# ── parse_jd ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_jd_extracts_keywords():
    jd = "Senior Python Engineer with AWS, Docker, Kubernetes. Must know FastAPI and PostgreSQL."
    result = await _parse_jd(jd_text=jd)
    assert "top_keywords" in result
    assert "keyword_frequency" in result
    assert "total_words" in result
    assert len(result["top_keywords"]) > 0
    # Python should be a top keyword
    lower_keywords = [k.lower() for k in result["top_keywords"]]
    assert "python" in lower_keywords


@pytest.mark.asyncio
async def test_parse_jd_handles_empty():
    result = await _parse_jd(jd_text="")
    assert result["total_words"] == 0
    assert result["top_keywords"] == []


# ── extract_profile_evidence ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_profile_evidence_full():
    profile = {
        "skills": [{"name": "Python"}, "React", {"name": "AWS"}],
        "experience": [
            {"title": "Engineer", "company": "Acme", "start_date": "2020", "end_date": "present"},
            {"title": "Intern", "company": "StartupX"},
        ],
        "education": [{"degree": "BS CS", "institution": "MIT"}],
        "certifications": [{"name": "AWS SA"}, "CKA"],
    }
    result = await _extract_profile_evidence(user_profile=profile)
    assert result["skills"] == ["Python", "React", "AWS"]
    assert result["companies"] == ["Acme", "StartupX"]
    assert result["titles"] == ["Engineer", "Intern"]
    assert result["experience_count"] == 2
    assert result["education_count"] == 1
    assert len(result["certifications"]) == 2


@pytest.mark.asyncio
async def test_extract_profile_evidence_empty():
    result = await _extract_profile_evidence(user_profile={})
    assert result["skills"] == []
    assert result["experience_count"] == 0


# ── compute_keyword_overlap ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_keyword_overlap():
    doc = "Python developer with FastAPI and PostgreSQL experience"
    jd = "Senior Python developer with FastAPI, AWS, and Kubernetes"
    result = await _compute_keyword_overlap(document_text=doc, jd_text=jd)
    assert 0 < result["match_ratio"] < 1
    assert "python" in [k.lower() for k in result["matched_keywords"]]
    assert len(result["missing_from_document"]) > 0


@pytest.mark.asyncio
async def test_keyword_overlap_empty_jd():
    result = await _compute_keyword_overlap(document_text="Python", jd_text="")
    assert result["match_ratio"] == 0


# ── compute_readability ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_readability_metrics():
    text = (
        "The engineer built a scalable system. "
        "It handled millions of requests per day. "
        "The team deployed using Docker and Kubernetes."
    )
    result = await _compute_readability(text=text)
    assert 0 <= result["flesch_reading_ease"] <= 100
    assert result["grade_level"] >= 0
    assert result["total_words"] > 0
    assert result["total_sentences"] == 3


@pytest.mark.asyncio
async def test_readability_empty():
    result = await _compute_readability(text="")
    # Empty text produces no real words; readability defaults apply
    assert result["total_sentences"] >= 1  # max(0, 1) floor
    assert result["flesch_reading_ease"] >= 0


# ── extract_claims ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_claims_finds_quantified():
    text = "Led a team of 5 engineers. Improved API latency by 40%. Generated $2M in revenue."
    result = await _extract_claims(document_text=text)
    assert result["total_claims_found"] >= 2
    claim_texts = [c["text"] for c in result["claims"]]
    # Should find the percentage claim
    assert any("40%" in t for t in claim_texts)


@pytest.mark.asyncio
async def test_extract_claims_finds_credentials():
    text = "Holds a B.S. in Computer Science from MIT. AWS Solutions Architect certified."
    result = await _extract_claims(document_text=text)
    assert result["total_claims_found"] >= 1


# ── match_claims_to_evidence ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_match_claims():
    claims = [
        {"text": "Built Python APIs at Acme Corp", "type": "quantified", "position": 0},
        {"text": "Led 50 person team at FakeCo", "type": "quantified", "position": 50},
    ]
    evidence = {
        "skills": ["Python", "FastAPI"],
        "companies": ["Acme Corp"],
        "titles": ["Engineer"],
        "certifications": [],
        "education": [],
    }
    result = await _match_claims_to_evidence(claims=claims, evidence=evidence)
    assert len(result["matched_claims"]) == 1  # Acme Corp + Python match
    assert len(result["unmatched_claims"]) == 1  # FakeCo is unmatched
    assert result["match_rate"] == 0.5


# ── Pre-built registries ─────────────────────────────────────────────

def test_fact_checker_tools_registry():
    reg = build_fact_checker_tools()
    names = {t.name for t in reg.list_tools()}
    assert names == {"extract_profile_evidence", "extract_claims", "match_claims_to_evidence"}


def test_optimizer_tools_registry():
    reg = build_optimizer_tools()
    names = {t.name for t in reg.list_tools()}
    assert names == {"compute_keyword_overlap", "compute_readability"}
