# backend/tests/unit/test_agents/test_sub_agents.py
"""Tests for sub-agent base infrastructure, all specialist sub-agents, and new tools."""
import pytest

from ai_engine.agents.sub_agents.base import (
    SubAgent,
    SubAgentResult,
    SubAgentCoordinator,
)
from ai_engine.agents.sub_agents.jd_analyst import JDAnalystSubAgent
from ai_engine.agents.sub_agents.profile_match_agent import ProfileMatchSubAgent
from ai_engine.agents.sub_agents.history_agent import HistorySubAgent
from ai_engine.agents.sub_agents.section_drafter import SectionDrafterSubAgent
from ai_engine.agents.sub_agents.critic_specialists import (
    ImpactCriticSubAgent,
    ClarityCriticSubAgent,
    ToneMatchCriticSubAgent,
    CompletenessCriticSubAgent,
)
from ai_engine.agents.sub_agents.fact_checker_specialists import (
    ClaimExtractorSubAgent,
    EvidenceMatcherSubAgent,
)
from ai_engine.agents.sub_agents.optimizer_specialists import (
    ATSOptimizerSubAgent,
    ReadabilityOptimizerSubAgent,
)


# ═══════════════════════════════════════════════════════════════════════
#  SubAgentResult
# ═══════════════════════════════════════════════════════════════════════

def test_sub_agent_result_ok_when_no_error():
    r = SubAgentResult(agent_name="test")
    assert r.ok is True


def test_sub_agent_result_not_ok_when_error():
    r = SubAgentResult(agent_name="test", error="boom")
    assert r.ok is False


def test_sub_agent_result_to_dict():
    r = SubAgentResult(
        agent_name="test",
        data={"key": "val"},
        confidence=0.85,
        latency_ms=100,
    )
    d = r.to_dict()
    assert d["agent_name"] == "test"
    assert d["data"] == {"key": "val"}
    assert d["confidence"] == 0.85
    assert d["latency_ms"] == 100
    assert d["error"] is None


# ═══════════════════════════════════════════════════════════════════════
#  SubAgent base (safe_run)
# ═══════════════════════════════════════════════════════════════════════

class _TestSubAgent(SubAgent):
    async def run(self, context: dict) -> SubAgentResult:
        return SubAgentResult(agent_name=self.name, data={"ok": True})


class _FailingSubAgent(SubAgent):
    async def run(self, context: dict) -> SubAgentResult:
        raise ValueError("intentional failure")


@pytest.mark.asyncio
async def test_safe_run_success():
    agent = _TestSubAgent(name="test")
    result = await agent.safe_run({})
    assert result.ok
    assert result.data == {"ok": True}
    assert result.latency_ms >= 0


@pytest.mark.asyncio
async def test_safe_run_catches_exception():
    agent = _FailingSubAgent(name="fail")
    result = await agent.safe_run({})
    assert not result.ok
    assert "intentional failure" in result.error


# ═══════════════════════════════════════════════════════════════════════
#  SubAgentCoordinator
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_coordinator_gather():
    agents = [_TestSubAgent(name="a"), _TestSubAgent(name="b")]
    coord = SubAgentCoordinator(agents)
    results = await coord.gather({})
    assert len(results) == 2
    assert all(r.ok for r in results)


@pytest.mark.asyncio
async def test_coordinator_tolerates_failure():
    agents = [_TestSubAgent(name="a"), _FailingSubAgent(name="fail")]
    coord = SubAgentCoordinator(agents)
    results = await coord.gather({})
    assert len(results) == 2
    assert results[0].ok
    assert not results[1].ok


def test_coordinator_agent_names():
    agents = [_TestSubAgent(name="x"), _TestSubAgent(name="y")]
    coord = SubAgentCoordinator(agents)
    assert coord.agent_names == ["x", "y"]


@pytest.mark.asyncio
async def test_coordinator_merge_evidence():
    r1 = SubAgentResult(agent_name="a", evidence_items=[{"fact": "f1"}])
    r2 = SubAgentResult(agent_name="b", evidence_items=[{"fact": "f2"}], error="oops")
    r3 = SubAgentResult(agent_name="c", evidence_items=[{"fact": "f3"}])
    coord = SubAgentCoordinator([])
    merged = coord.merge_evidence([r1, r2, r3])
    assert len(merged) == 2  # r2 has error, excluded
    assert merged[0]["fact"] == "f1"


@pytest.mark.asyncio
async def test_coordinator_merge_data():
    r1 = SubAgentResult(agent_name="a", data={"key": 1})
    r2 = SubAgentResult(agent_name="b", data={"key": 2})
    coord = SubAgentCoordinator([])
    merged = coord.merge_data([r1, r2])
    assert merged == {"a": {"key": 1}, "b": {"key": 2}}


# ═══════════════════════════════════════════════════════════════════════
#  JDAnalystSubAgent
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_jd_analyst_no_jd():
    agent = JDAnalystSubAgent()
    result = await agent.safe_run({})
    assert not result.ok
    assert "jd_text" in result.error


@pytest.mark.asyncio
async def test_jd_analyst_with_jd():
    agent = JDAnalystSubAgent()
    ctx = {
        "jd_text": "We are looking for a Senior Python Developer with 5+ years experience in Django and FastAPI. Must have AWS experience.",
    }
    result = await agent.safe_run(ctx)
    assert result.ok
    assert "parsed_jd" in result.data
    assert "sentiment" in result.data
    assert result.confidence > 0


@pytest.mark.asyncio
async def test_jd_analyst_with_profile():
    agent = JDAnalystSubAgent()
    ctx = {
        "jd_text": "Looking for Python developer with Django experience",
        "user_profile": {"resume_text": "Python developer with 5 years Django"},
    }
    result = await agent.safe_run(ctx)
    assert result.ok
    assert "keyword_overlap" in result.data


# ═══════════════════════════════════════════════════════════════════════
#  ProfileMatchSubAgent
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_profile_match_no_profile():
    agent = ProfileMatchSubAgent()
    result = await agent.safe_run({"jd_text": "some jd"})
    assert result.ok
    assert result.confidence == 0.30
    assert "note" in result.data


@pytest.mark.asyncio
async def test_profile_match_with_profile():
    agent = ProfileMatchSubAgent()
    ctx = {
        "user_profile": {
            "resume_text": "I am a Python developer with 5 years of experience.",
            "skills": ["Python", "Django"],
        },
        "jd_text": "Looking for Python developer",
    }
    result = await agent.safe_run(ctx)
    assert result.ok
    assert "profile_evidence" in result.data


# ═══════════════════════════════════════════════════════════════════════
#  HistorySubAgent
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_history_no_db():
    agent = HistorySubAgent()
    result = await agent.safe_run({})
    assert result.ok  # Returns gracefully with low confidence
    assert result.confidence == 0.30


# ═══════════════════════════════════════════════════════════════════════
#  New Research Tools (deterministic)
# ═══════════════════════════════════════════════════════════════════════

from ai_engine.agents.tools import _analyze_jd_sentiment  # noqa: E402


@pytest.mark.asyncio
async def test_jd_sentiment_empty():
    result = await _analyze_jd_sentiment(jd_text="")
    assert "error" in result


@pytest.mark.asyncio
async def test_jd_sentiment_urgency():
    result = await _analyze_jd_sentiment(
        jd_text="We need someone immediately in this fast-paced startup environment."
    )
    assert result["urgency_level"] in ("medium", "high")
    assert len(result["urgency_signals"]) >= 1


@pytest.mark.asyncio
async def test_jd_sentiment_red_flags():
    result = await _analyze_jd_sentiment(
        jd_text="We're like a family here. Looking for a rockstar who can wear many hats."
    )
    assert result["red_flag_count"] >= 2


@pytest.mark.asyncio
async def test_jd_sentiment_seniority():
    result = await _analyze_jd_sentiment(
        jd_text="Senior Software Engineer with 8+ years of experience leading teams."
    )
    assert result["seniority_level"] == "senior"


@pytest.mark.asyncio
async def test_jd_sentiment_junior():
    result = await _analyze_jd_sentiment(
        jd_text="Entry level position for recent graduates. 0-2 years experience."
    )
    assert result["seniority_level"] == "junior"


@pytest.mark.asyncio
async def test_jd_sentiment_remote():
    result = await _analyze_jd_sentiment(
        jd_text="This is a fully remote position with flexible hours."
    )
    assert result["work_mode"] == "remote"


@pytest.mark.asyncio
async def test_jd_sentiment_salary():
    result = await _analyze_jd_sentiment(
        jd_text="Salary range: $120,000 - $150,000 with equity and stock options."
    )
    assert len(result["salary_mentioned"]) >= 1
    assert result["equity_mentioned"] is True


@pytest.mark.asyncio
async def test_jd_sentiment_team_size():
    result = await _analyze_jd_sentiment(
        jd_text="You'll join a team of 12 engineers working on cloud infrastructure."
    )
    assert result["team_size"] == 12


# ═══════════════════════════════════════════════════════════════════════
#  Tool Registry — new tools registered
# ═══════════════════════════════════════════════════════════════════════

from ai_engine.agents.tools import build_researcher_tools  # noqa: E402


def test_researcher_tools_include_new_deep_research_tools():
    """Verify all 7 new deep-research tools are registered."""
    reg = build_researcher_tools()
    tools = reg.list_tools()
    names = {t.name for t in tools}
    new_tools = {
        "search_glassdoor_reviews",
        "search_linkedin_insights",
        "search_company_news",
        "search_competitor_landscape",
        "search_tech_blog",
        "analyze_jd_sentiment",
        "cross_reference_job_postings",
    }
    for tool_name in new_tools:
        assert tool_name in names, f"Missing tool: {tool_name}"


def test_researcher_tools_count_increased():
    """Verify the total tool count is 3 (core) + 3 (v3 external) + 7 (v3.1 deep) = 13."""
    reg = build_researcher_tools()
    tools = reg.list_tools()
    assert len(tools) >= 13


# ═══════════════════════════════════════════════════════════════════════
#  Critic specialists (structure only — no LLM)
# ═══════════════════════════════════════════════════════════════════════

def test_critic_specialist_names():
    assert ImpactCriticSubAgent().name == "critic:impact"
    assert ClarityCriticSubAgent().name == "critic:clarity"
    assert ToneMatchCriticSubAgent().name == "critic:tone_match"
    assert CompletenessCriticSubAgent().name == "critic:completeness"


@pytest.mark.asyncio
async def test_critic_specialist_no_draft():
    agent = ImpactCriticSubAgent()
    result = await agent.safe_run({})
    assert not result.ok
    assert "draft" in result.error.lower() or "content" in result.error.lower()


# ═══════════════════════════════════════════════════════════════════════
#  FactChecker specialists
# ═══════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_claim_extractor_empty():
    agent = ClaimExtractorSubAgent()
    result = await agent.safe_run({"draft_content": {}})
    # No text → error
    assert not result.ok


@pytest.mark.asyncio
async def test_claim_extractor_with_text():
    agent = ClaimExtractorSubAgent()
    result = await agent.safe_run({
        "draft_content": {
            "summary": "Led a team of 10 engineers to deliver $5M project on time."
        }
    })
    assert result.ok
    assert "claims" in result.data


@pytest.mark.asyncio
async def test_evidence_matcher_no_profile():
    agent = EvidenceMatcherSubAgent()
    result = await agent.safe_run({"claims": [{"text": "test"}]})
    assert not result.ok


# ═══════════════════════════════════════════════════════════════════════
#  Optimizer specialists
# ═══════════════════════════════════════════════════════════════════════

def test_optimizer_specialist_names():
    assert ATSOptimizerSubAgent().name == "optimizer:ats"
    assert ReadabilityOptimizerSubAgent().name == "optimizer:readability"


@pytest.mark.asyncio
async def test_readability_optimizer_with_text():
    agent = ReadabilityOptimizerSubAgent()
    result = await agent.safe_run({
        "draft_content": {
            "text": "This is a sample document with several sentences. "
                    "It has good readability and clear structure. "
                    "The candidate has excellent skills in Python programming."
        }
    })
    assert result.ok
    assert "readability_score" in result.data
    assert "quality_band" in result.data


@pytest.mark.asyncio
async def test_ats_optimizer_needs_both_texts():
    agent = ATSOptimizerSubAgent()
    result = await agent.safe_run({"draft_content": {"text": "some text"}})
    assert not result.ok  # No jd_text


# ═══════════════════════════════════════════════════════════════════════
#  SectionDrafter
# ═══════════════════════════════════════════════════════════════════════

def test_section_drafter_name():
    agent = SectionDrafterSubAgent(section_name="summary")
    assert agent.name == "section_drafter:summary"


@pytest.mark.asyncio
async def test_section_drafter_no_section():
    agent = SectionDrafterSubAgent()
    result = await agent.safe_run({})
    assert not result.ok


# ═══════════════════════════════════════════════════════════════════════
#  Evidence Ledger enhancements
# ═══════════════════════════════════════════════════════════════════════

from ai_engine.agents.evidence import EvidenceLedger, EvidenceSource, EvidenceTier  # noqa: E402


def test_evidence_add_with_confidence():
    ledger = EvidenceLedger()
    item = ledger.add(EvidenceTier.VERBATIM, EvidenceSource.JD, "test_field", "fact1", confidence=0.95)
    assert item.confidence == 0.95


def test_evidence_add_with_sub_agent():
    ledger = EvidenceLedger()
    item = ledger.add(EvidenceTier.DERIVED, EvidenceSource.JD, "test_field", "fact1", sub_agent="company_intel")
    assert "company_intel" in item.confirmed_by


def test_evidence_confirm():
    ledger = EvidenceLedger()
    item = ledger.add(EvidenceTier.DERIVED, EvidenceSource.JD, "test_field", "fact1")
    initial_conf = item.confidence
    ledger.confirm(item.id, "test_agent")
    assert "test_agent" in ledger._items[item.id].confirmed_by
    assert ledger._items[item.id].confidence > initial_conf


def test_evidence_find_high_confidence():
    ledger = EvidenceLedger()
    item1 = ledger.add(EvidenceTier.VERBATIM, EvidenceSource.PROFILE, "f1", "high", confidence=0.95)
    item2 = ledger.add(EvidenceTier.INFERRED, EvidenceSource.PROFILE, "f2", "low", confidence=0.30)
    high = ledger.find_high_confidence(threshold=0.80)
    assert item1.id in [e.id for e in high]
    assert item2.id not in [e.id for e in high]


def test_evidence_to_dict_from_dict_roundtrip():
    ledger = EvidenceLedger()
    ledger.add(EvidenceTier.VERBATIM, EvidenceSource.JD, "test_field", "fact1", confidence=0.88, sub_agent="test")
    data = ledger.to_dict()
    restored = EvidenceLedger.from_dict(data)
    assert len(restored._items) == len(ledger._items)
    for eid, item in ledger._items.items():
        restored_item = restored._items[eid]
        assert restored_item.confidence == item.confidence
        assert restored_item.confirmed_by == item.confirmed_by


# ═══════════════════════════════════════════════════════════════════════
#  ResearchDepth
# ═══════════════════════════════════════════════════════════════════════

from ai_engine.agents.researcher import ResearchDepth, _DEPTH_CONFIG  # noqa: E402


def test_research_depth_configs():
    assert ResearchDepth.QUICK.value == "quick"
    assert ResearchDepth.THOROUGH.value == "thorough"
    assert ResearchDepth.EXHAUSTIVE.value == "exhaustive"
    # Verify config values increase with depth
    q = _DEPTH_CONFIG[ResearchDepth.QUICK]
    t = _DEPTH_CONFIG[ResearchDepth.THOROUGH]
    e = _DEPTH_CONFIG[ResearchDepth.EXHAUSTIVE]
    assert q[0] < t[0] < e[0]  # max_tool_steps
    assert q[1] < t[1] < e[1]  # coverage_threshold


# ═══════════════════════════════════════════════════════════════════════
#  Pipeline factory with sub-agents
# ═══════════════════════════════════════════════════════════════════════

def test_create_pipeline_attaches_sub_agents():
    """Verify create_pipeline attaches sub-agents for THOROUGH depth."""
    from ai_engine.agents.pipelines import create_pipeline
    from ai_engine.chains.universal_doc_generator import UniversalDocGeneratorChain
    from ai_engine.client import get_ai_client

    client = get_ai_client()
    chain = UniversalDocGeneratorChain(client)
    pipeline = create_pipeline(
        "test_pipeline",
        chain,
        "generate",
        ai_client=client,
        research_depth=ResearchDepth.THOROUGH,
    )
    assert pipeline.researcher is not None
    assert len(pipeline.researcher._sub_agents) == 5
