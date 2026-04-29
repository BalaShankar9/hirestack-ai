"""S5-F2 — Pin _validate_result contracts across the 7 chains.

Every public chain that calls an LLM ends with a `_validate_result`
defensive normaliser. These helpers are the LAST line of defence
between unreliable LLM output and persisted user data — if the model
returns half a payload (or none), the validator MUST backfill the
expected keys with safe defaults so downstream code doesn't crash.

Drift here is invisible until a customer hits a 500.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from ai_engine.chains.career_consultant import CareerConsultantChain
from ai_engine.chains.gap_analyzer import GapAnalyzerChain
from ai_engine.chains.learning_challenge import LearningChallengeChain
from ai_engine.chains.linkedin_advisor import LinkedInAdvisorChain
from ai_engine.chains.market_intelligence import MarketIntelligenceChain
from ai_engine.chains.role_profiler import RoleProfilerChain
from ai_engine.chains.salary_coach import SalaryCoachChain


# ── GapAnalyzerChain ──────────────────────────────────────────────────


def test_gap_validate_clamps_compatibility_score_low() -> None:
    chain = GapAnalyzerChain(MagicMock())
    out = chain._validate_result({"compatibility_score": -50})
    assert out["compatibility_score"] == 0


def test_gap_validate_clamps_compatibility_score_high() -> None:
    chain = GapAnalyzerChain(MagicMock())
    out = chain._validate_result({"compatibility_score": 200})
    assert out["compatibility_score"] == 100


def test_gap_validate_backfills_required_keys() -> None:
    """Pin every key the downstream Atlas/Database paths read. Adding
    a key to the chain without adding it to defaults is a crash bug."""
    chain = GapAnalyzerChain(MagicMock())
    out = chain._validate_result({})
    for key in (
        "compatibility_score",
        "readiness_level",
        "executive_summary",
        "category_scores",
        "skill_gaps",
        "experience_gaps",
        "education_gaps",
        "certification_gaps",
        "project_gaps",
        "strengths",
        "recommendations",
        "quick_wins",
        "long_term_investments",
        "interview_readiness",
    ):
        assert key in out, f"_validate_result missing default for '{key}'"


def test_gap_validate_drops_string_recommendations() -> None:
    """LLM occasionally returns recommendations as bare strings.
    These would crash the priority sort. Drop them silently."""
    chain = GapAnalyzerChain(MagicMock())
    out = chain._validate_result(
        {"recommendations": [{"priority": 1, "title": "A"}, "junk", {"priority": 2}]}
    )
    assert all(isinstance(r, dict) for r in out["recommendations"])


def test_gap_validate_sorts_recommendations_by_priority() -> None:
    chain = GapAnalyzerChain(MagicMock())
    out = chain._validate_result(
        {"recommendations": [{"priority": 5}, {"priority": 1}, {"priority": 3}]}
    )
    assert [r["priority"] for r in out["recommendations"]] == [1, 3, 5]


def test_gap_validate_handles_recommendation_without_priority() -> None:
    """Missing-priority recommendations should sort last (priority 99
    fallback) without crashing."""
    chain = GapAnalyzerChain(MagicMock())
    out = chain._validate_result(
        {"recommendations": [{"title": "no-prio"}, {"priority": 1}]}
    )
    # Priority-1 first, no-prio last
    assert out["recommendations"][0].get("priority") == 1


# ── CareerConsultantChain ─────────────────────────────────────────────


def test_career_validate_backfills_keys() -> None:
    chain = CareerConsultantChain(MagicMock())
    out = chain._validate_result({})
    for key in (
        "roadmap",
        "learning_resources",
        "tools_recommended",
        "motivation_tips",
        "common_pitfalls",
    ):
        assert key in out


def test_career_validate_preserves_existing_values() -> None:
    chain = CareerConsultantChain(MagicMock())
    out = chain._validate_result({"motivation_tips": ["keep going"]})
    assert out["motivation_tips"] == ["keep going"]


# ── LinkedInAdvisorChain ──────────────────────────────────────────────


def test_linkedin_validate_backfills_keys() -> None:
    out = LinkedInAdvisorChain._validate_result({})
    for key in (
        "headline_suggestions",
        "summary_rewrite",
        "skills_to_add",
        "experience_improvements",
        "profile_completeness_tips",
        "overall_score",
        "priority_actions",
    ):
        assert key in out


def test_linkedin_validate_default_overall_score_is_50() -> None:
    out = LinkedInAdvisorChain._validate_result({})
    assert out["overall_score"] == 50


def test_linkedin_validate_preserves_existing_overall_score() -> None:
    out = LinkedInAdvisorChain._validate_result({"overall_score": 90})
    assert out["overall_score"] == 90


# ── MarketIntelligenceChain ───────────────────────────────────────────


def test_market_validate_backfills_keys() -> None:
    out = MarketIntelligenceChain._validate_result({})
    for key in (
        "market_overview",
        "skills_demand",
        "emerging_trends",
        "salary_insights",
        "opportunity_suggestions",
        "skill_gaps_to_market",
    ):
        assert key in out


def test_market_validate_market_overview_has_temperature_and_summary() -> None:
    out = MarketIntelligenceChain._validate_result({})
    assert out["market_overview"]["temperature"] == "warm"
    assert "summary" in out["market_overview"]


def test_market_validate_salary_insights_has_currency_and_range() -> None:
    out = MarketIntelligenceChain._validate_result({})
    assert out["salary_insights"]["currency"] == "USD"
    for key in ("range_low", "range_median", "range_high"):
        assert key in out["salary_insights"]


# ── SalaryCoachChain ──────────────────────────────────────────────────


def test_salary_validate_backfills_keys() -> None:
    chain = SalaryCoachChain(MagicMock())
    out = chain._validate_result({})
    for key in (
        "market_analysis",
        "candidate_value_assessment",
        "negotiation_strategy",
        "negotiation_scripts",
        "talking_points",
        "red_flags",
        "total_compensation_tips",
        "overall_assessment",
    ):
        assert key in out


# ── LearningChallengeChain ────────────────────────────────────────────


def test_learning_validate_backfills_keys() -> None:
    chain = LearningChallengeChain(MagicMock())
    out = chain._validate_result({})
    for key in (
        "title",
        "description",
        "difficulty",
        "estimated_hours",
        "skill",
        "learning_objectives",
        "steps",
        "resources",
        "success_criteria",
        "portfolio_output",
        "next_challenge",
    ):
        assert key in out


def test_learning_validate_default_difficulty_is_intermediate() -> None:
    chain = LearningChallengeChain(MagicMock())
    out = chain._validate_result({})
    assert out["difficulty"] == "intermediate"


def test_learning_validate_default_estimated_hours_is_eight() -> None:
    chain = LearningChallengeChain(MagicMock())
    out = chain._validate_result({})
    assert out["estimated_hours"] == 8.0


# ── RoleProfilerChain (already covered structurally; sanity check) ────


def test_role_profiler_validate_backfills_required_keys() -> None:
    """Sanity: F1 covers helpers individually; this pins the umbrella
    contract that _validate_result restores ALL persisted keys."""
    chain = RoleProfilerChain(MagicMock())
    out = chain._validate_result({})
    for key in (
        "name",
        "title",
        "summary",
        "contact_info",
        "skills",
        "experience",
        "education",
        "certifications",
        "projects",
        "languages",
        "achievements",
    ):
        assert key in out


def test_role_profiler_validate_emits_parse_confidence_and_warnings() -> None:
    """Two derived fields the frontend depends on; their absence
    triggers a NaN gauge in the UI."""
    chain = RoleProfilerChain(MagicMock())
    out = chain._validate_result({})
    assert "parse_confidence" in out
    assert "parse_warnings" in out
    assert isinstance(out["parse_confidence"], float)
    assert isinstance(out["parse_warnings"], list)


def test_role_profiler_validate_handles_non_dict_input() -> None:
    """Defensive: if the LLM returns a list / string, validator must
    reset to defaults rather than crash."""
    chain = RoleProfilerChain(MagicMock())
    out = chain._validate_result(["junk"])  # type: ignore[arg-type]
    assert out["name"] is None
    assert out["skills"] == []
