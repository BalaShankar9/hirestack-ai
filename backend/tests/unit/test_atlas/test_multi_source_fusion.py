"""Unit tests for ATLAS CandidateFusion."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ai_engine.agents.artifact_contracts import (
    CandidateProfile,
    CandidateSkill,
    ImpactSignal,
    SkillProvenance,
)
from ai_engine.agents.sub_agents.atlas.multi_source_fusion import (
    CandidateFusion,
    _bucket_to_skill,
    _months_since,
    _parse_iso_date,
    _SkillBucket,
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,ok",
    [
        ("2025-01-15", True),
        ("2025-01-15T12:34:56", True),
        ("2025-01-15T12:34:56Z", True),
        ("2025-01-15T12:34:56+00:00", True),
        ("not-a-date", False),
        ("", False),
        (None, False),
        (12345, False),
    ],
)
def test_parse_iso_date(raw, ok):
    out = _parse_iso_date(raw)
    if ok:
        assert isinstance(out, datetime)
    else:
        assert out is None


def test_months_since():
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    dt = datetime(2024, 5, 1, tzinfo=timezone.utc)
    months = _months_since(dt, now=now)
    assert 23.5 <= months <= 24.5


def test_months_since_naive_input_treated_as_utc():
    now = datetime(2026, 5, 1, tzinfo=timezone.utc)
    dt = datetime(2026, 4, 1)  # naive
    months = _months_since(dt, now=now)
    assert 0.9 <= months <= 1.1


# ---------------------------------------------------------------------------
# _bucket_to_skill — level + decay
# ---------------------------------------------------------------------------

def test_bucket_to_skill_levels():
    b = _SkillBucket(name="Python")
    b.add(SkillProvenance(source="resume", confidence=0.9))
    skill = _bucket_to_skill(b)
    assert skill.level == "expert"
    assert skill.proficiency == 0.9
    assert skill.verified is False  # only one source

    b2 = _SkillBucket(name="Go")
    b2.add(SkillProvenance(source="resume", confidence=0.7))
    b2.add(SkillProvenance(source="github_user", confidence=0.6))
    skill2 = _bucket_to_skill(b2)
    assert skill2.level == "advanced"
    assert skill2.verified is True  # two sources


def test_bucket_to_skill_intermediate_and_beginner():
    mid = _SkillBucket(name="Rust")
    mid.add(SkillProvenance(source="resume", confidence=0.5))
    assert _bucket_to_skill(mid).level == "intermediate"

    low = _SkillBucket(name="COBOL")
    low.add(SkillProvenance(source="resume", confidence=0.3))
    assert _bucket_to_skill(low).level == "beginner"


def test_bucket_to_skill_decay_applied_when_stale():
    """last_used_at older than 36mo -> proficiency *= 0.7"""
    long_ago = (datetime.now(timezone.utc) - timedelta(days=365 * 5)).strftime("%Y-%m-%d")
    b = _SkillBucket(name="Perl")
    b.add(SkillProvenance(source="resume", confidence=0.9, last_used_at=long_ago))
    skill = _bucket_to_skill(b)
    assert abs(skill.proficiency - (0.9 * 0.7)) < 1e-3
    # decayed below 0.65 -> intermediate
    assert skill.level == "intermediate"


def test_bucket_to_skill_no_decay_when_recent():
    recent = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%d")
    b = _SkillBucket(name="Python")
    b.add(SkillProvenance(source="github_user", confidence=0.9, last_used_at=recent))
    assert _bucket_to_skill(b).proficiency == 0.9


# ---------------------------------------------------------------------------
# CandidateFusion.fuse — end-to-end
# ---------------------------------------------------------------------------

def test_fuse_resume_only_produces_profile():
    fusion = CandidateFusion()
    out = fusion.fuse(
        candidate_name="Ada Lovelace",
        resume_skills=["Python", "Rust", "SQL"],
        resume_evidence={"python": "Wrote async services in Python."},
    )
    assert isinstance(out, CandidateProfile)
    assert out.candidate_name == "Ada Lovelace"
    names = {s.name for s in out.skills}
    assert names == {"Python", "Rust", "SQL"}
    py = next(s for s in out.skills if s.name == "Python")
    assert py.provenance[0].source == "resume"
    assert "Wrote async" in py.provenance[0].evidence
    assert out.sources_used == ["resume"]


def test_fuse_github_top_languages_ranked_confidence():
    fusion = CandidateFusion()
    out = fusion.fuse(
        github={
            "top_languages": ["Python", "TypeScript", "Go"],
            "most_recent_push": "2026-04-01",
        },
    )
    by_name = {s.name: s for s in out.skills}
    assert by_name["Python"].proficiency >= by_name["TypeScript"].proficiency
    assert by_name["TypeScript"].proficiency >= by_name["Go"].proficiency
    # All carry github_user provenance
    for s in out.skills:
        assert s.provenance[0].source == "github_user"
    assert out.sources_used == ["github_user"]


def test_fuse_two_sources_mark_verified():
    fusion = CandidateFusion()
    out = fusion.fuse(
        resume_skills=["Python"],
        github={"top_languages": ["Python"], "most_recent_push": "2026-04-01"},
    )
    py = next(s for s in out.skills if s.name == "Python")
    assert py.verified is True
    assert {p.source for p in py.provenance} == {"resume", "github_user"}
    # max confidence = 0.9 (github top1)
    assert py.proficiency == 0.9


def test_fuse_linkedin_boosts_existing_skill_only():
    fusion = CandidateFusion()
    out = fusion.fuse(
        resume_skills=["Python", "Kubernetes"],
        linkedin={
            "name": "Jane",
            "headline": "Senior Python Engineer at Stripe",
            "description": "I love distributed systems.",
        },
    )
    py = next(s for s in out.skills if s.name == "Python")
    assert any(p.source == "linkedin_public" for p in py.provenance)
    k8s = next(s for s in out.skills if s.name == "Kubernetes")
    assert all(p.source != "linkedin_public" for p in k8s.provenance)


def test_fuse_linkedin_does_not_invent_new_skills():
    fusion = CandidateFusion()
    out = fusion.fuse(
        linkedin={
            "headline": "Full-Stack Engineer | Rust enthusiast",
            "description": "JavaScript, TypeScript, Postgres.",
        },
    )
    # Resume gave nothing, GitHub gave nothing — LinkedIn should NOT
    # invent skills because we never seeded the bucket.
    assert out.skills == []


def test_fuse_pulls_name_and_headline_from_linkedin_when_missing():
    fusion = CandidateFusion()
    out = fusion.fuse(
        linkedin={
            "name": "Grace Hopper",
            "headline": "Rear Admiral",
            "description": "Cobol pioneer.",
        },
    )
    assert out.candidate_name == "Grace Hopper"
    assert out.headline == "Rear Admiral"
    assert out.summary == "Cobol pioneer."


def test_fuse_explicit_args_override_linkedin():
    fusion = CandidateFusion()
    out = fusion.fuse(
        candidate_name="Override Name",
        headline="Custom Headline",
        linkedin={"name": "From LinkedIn", "headline": "From LI"},
    )
    assert out.candidate_name == "Override Name"
    assert out.headline == "Custom Headline"


def test_fuse_skills_capped_at_max():
    fusion = CandidateFusion()
    many_skills = [f"Skill{i}" for i in range(50)]
    out = fusion.fuse(resume_skills=many_skills)
    assert len(out.skills) == 20  # _MAX_SKILLS


def test_fuse_passes_through_impact_signals_and_lists():
    fusion = CandidateFusion()
    impacts = [ImpactSignal(metric="users", value="10M", confidence=0.7)]
    exp = [{"company": "Acme", "title": "SWE"}]
    edu = [{"school": "MIT", "degree": "BS"}]
    out = fusion.fuse(
        resume_skills=["Python"],
        impact_signals=impacts,
        experience=exp,
        education=edu,
        years_experience=8.5,
    )
    assert out.impact_signals == impacts
    assert out.experience == exp
    assert out.education == edu
    assert out.years_experience == 8.5


def test_fuse_empty_inputs_returns_empty_profile():
    fusion = CandidateFusion()
    out = fusion.fuse()
    assert isinstance(out, CandidateProfile)
    assert out.skills == []
    assert out.sources_used == []
    assert out.candidate_name == ""


def test_fuse_handles_malformed_inputs_gracefully():
    fusion = CandidateFusion()
    out = fusion.fuse(
        resume_skills=["", "  ", None, "Python"],   # filters empties
        github={"top_languages": "not a list"},     # ignored
        linkedin="not a dict",                       # ignored
    )
    assert [s.name for s in out.skills] == ["Python"]


def test_fuse_normalization_collapses_case_variants():
    fusion = CandidateFusion()
    out = fusion.fuse(
        resume_skills=["PYTHON"],
        github={"top_languages": ["python"], "most_recent_push": "2026-04-01"},
    )
    # Should fuse into ONE bucket (case-insensitive normalize).
    pys = [s for s in out.skills if s.name.lower() == "python"]
    assert len(pys) == 1
    assert pys[0].verified is True


def test_fuse_sources_used_order_and_membership():
    fusion = CandidateFusion()
    out = fusion.fuse(
        resume_skills=["Python"],
        github={"top_languages": ["Python"], "most_recent_push": "2026-04-01"},
        linkedin={"headline": "Python Engineer"},
    )
    assert out.sources_used == ["resume", "github_user", "linkedin_public"]


def test_fuse_decay_changes_proficiency():
    fusion = CandidateFusion()
    long_ago = "2018-01-01"
    out = fusion.fuse(
        github={"top_languages": ["Cobol"], "most_recent_push": long_ago},
    )
    cobol = out.skills[0]
    # Top language confidence 0.9 -> decay 0.9 * 0.7 = 0.63
    assert abs(cobol.proficiency - 0.63) < 1e-3
