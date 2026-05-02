"""Phase 0.1 — additive ATLAS v2 artifact contracts.

These tests pin the new types added to ``artifact_contracts.py`` for the
ATLAS rebuild (CandidateProfile, Archetype, ImpactSignal,
CandidateValidationReport). They verify:

  - the types instantiate with sensible defaults
  - JSON round-trip works (so they can land in agent_artifacts.content)
  - they are registered in the ARTIFACT_TYPES dispatch table
  - the existing Sentinel ``ValidationReport`` was NOT clobbered
  - the existing ``BenchmarkProfile`` was NOT modified
"""
from __future__ import annotations

import json

import pytest

from ai_engine.agents.artifact_contracts import (
    ARTIFACT_TYPES,
    Archetype,
    BenchmarkProfile,
    CandidateProfile,
    CandidateSkill,
    CandidateValidationClaim,
    CandidateValidationReport,
    ImpactSignal,
    SkillProvenance,
    ValidationReport,
    artifact_for_type,
)


def test_skill_provenance_minimal():
    sp = SkillProvenance(source="resume")
    assert sp.source == "resume"
    assert sp.confidence == 0.5
    assert sp.evidence == ""
    assert sp.last_used_at is None


def test_candidate_skill_defaults_and_provenance():
    sk = CandidateSkill(
        name="Python",
        provenance=[
            SkillProvenance(source="resume", confidence=0.9, evidence="5y FastAPI"),
            SkillProvenance(source="github_user", confidence=0.8, evidence="200 commits/yr"),
        ],
        verified=True,
    )
    assert sk.name == "Python"
    assert sk.level == "intermediate"
    assert sk.years == 0.0
    assert len(sk.provenance) == 2
    assert sk.verified is True


def test_impact_signal_round_trip():
    sig = ImpactSignal(metric="users", value="10M+", confidence=0.7, evidence="grew DAU to 10M+")
    payload = sig.model_dump()
    restored = ImpactSignal(**payload)
    assert restored == sig


def test_candidate_profile_defaults():
    cp = CandidateProfile(application_id="app-1", created_by_agent="atlas.fusion")
    assert cp.candidate_name == ""
    assert cp.skills == []
    assert cp.impact_signals == []
    assert cp.sources_used == []
    assert cp.application_id == "app-1"


def test_candidate_profile_json_round_trip():
    cp = CandidateProfile(
        candidate_name="Ada Lovelace",
        headline="Staff Engineer",
        skills=[
            CandidateSkill(
                name="Python",
                level="expert",
                years=8.0,
                proficiency=0.95,
                provenance=[SkillProvenance(source="resume", confidence=0.95)],
                verified=True,
            )
        ],
        impact_signals=[ImpactSignal(metric="revenue", value="$2.4M ARR")],
        sources_used=["resume", "github_user"],
    )
    data = json.loads(cp.model_dump_json())
    restored = CandidateProfile(**data)
    assert restored.candidate_name == "Ada Lovelace"
    assert restored.skills[0].verified is True
    assert restored.impact_signals[0].metric == "revenue"


def test_archetype_defaults():
    a = Archetype(name="Stripe Senior Eng")
    assert a.name == "Stripe Senior Eng"
    assert a.must_have_skills == []
    assert a.years_min == 0
    assert a.salary_band == {}


def test_archetype_full():
    a = Archetype(
        name="OpenAI Research Eng",
        must_have_skills=["python", "pytorch"],
        nice_to_have_skills=["cuda"],
        years_min=4,
        years_max=8,
        salary_band={"p50": 320000, "currency": "USD"},
        cultural_signals=["fast iteration"],
        rationale="JD emphasizes ML infra at scale",
    )
    assert a.years_max == 8
    assert a.salary_band["p50"] == 320000


def test_candidate_validation_report_defaults():
    rep = CandidateValidationReport()
    assert rep.claims == []
    assert rep.verified_count == 0
    assert rep.conflicted_count == 0


def test_candidate_validation_report_with_claims():
    rep = CandidateValidationReport(
        claims=[
            CandidateValidationClaim(
                claim="5 years Python",
                validator="github_commits",
                status="verified",
                detail="oldest python commit 2019-03",
            ),
            CandidateValidationClaim(
                claim="Worked at FakeCo Ltd",
                validator="company_exists",
                status="conflicted",
                detail="No Wikidata match",
            ),
        ],
        verified_count=1,
        conflicted_count=1,
    )
    assert rep.verified_count == 1
    assert rep.claims[1].status == "conflicted"


def test_artifact_types_registry_includes_new_types():
    assert ARTIFACT_TYPES["CandidateProfile"] is CandidateProfile
    assert ARTIFACT_TYPES["CandidateValidationReport"] is CandidateValidationReport
    # And they're reachable through the lookup helper
    assert artifact_for_type("CandidateProfile") is CandidateProfile
    assert artifact_for_type("CandidateValidationReport") is CandidateValidationReport


def test_existing_sentinel_validation_report_untouched():
    """Defensive: the original Sentinel ValidationReport must keep its shape."""
    rep = ValidationReport(overall_score=88.5, docs_passed=["resume"], docs_failed=[])
    assert rep.overall_score == 88.5
    # Sentinel ValidationReport still has `findings`/`docs_passed`/`docs_failed`
    assert hasattr(rep, "findings")
    assert hasattr(rep, "docs_passed")
    # And the new Atlas type is a *different* class
    assert ValidationReport is not CandidateValidationReport


def test_existing_benchmark_profile_untouched():
    bp = BenchmarkProfile(job_title="SWE", company="Acme")
    assert bp.job_title == "SWE"
    assert bp.skills == []
    # New fields from Atlas v2 must NOT have leaked into BenchmarkProfile
    assert not hasattr(bp, "impact_signals")
    assert not hasattr(bp, "sources_used")


def test_candidate_profile_extra_field_forbidden():
    """ArtifactBase enforces extra='forbid' — typos must fail loudly."""
    with pytest.raises(Exception):
        CandidateProfile(candidate_name="x", bogus_field=True)  # type: ignore[call-arg]
