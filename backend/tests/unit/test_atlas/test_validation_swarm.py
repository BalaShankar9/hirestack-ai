"""Unit tests for ATLAS ValidationSwarm."""
from __future__ import annotations

import asyncio
import json

import pytest

from ai_engine.agents.artifact_contracts import (
    CandidateProfile,
    CandidateSkill,
    CandidateValidationClaim,
    SkillProvenance,
)
from ai_engine.agents.sub_agents.atlas.validation_swarm import (
    CompanyExistsValidator,
    DateConsistencyValidator,
    GitHubCommitValidator,
    ValidationSwarm,
    _months_between,
    _normalize_lang,
    _parse_date,
)


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

class _FakeResp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    """Minimal AsyncClient stand-in routed by `search` query string."""

    def __init__(self, route_map):
        # route_map: {company_lower: _FakeResp | Exception}
        self._routes = route_map
        self.calls = []
        self.closed = False

    async def get(self, url, params=None, **kw):
        params = params or {}
        company = (params.get("search") or "").lower()
        self.calls.append({"url": url, "params": params})
        for key, val in self._routes.items():
            if key.lower() in company or company in key.lower():
                if isinstance(val, Exception):
                    raise val
                return val
        # Default: empty hit
        return _FakeResp(200, {"search": []})

    async def aclose(self):
        self.closed = True


def _profile(*, skills=None, experience=None, sources_used=None):
    return CandidateProfile(
        candidate_name="Test User",
        skills=skills or [],
        experience=experience or [],
        sources_used=sources_used or [],
        created_by_agent="test",
    )


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

def test_normalize_lang_aliases():
    assert _normalize_lang("Node.js") == "javascript"
    assert _normalize_lang("TS") == "typescript"
    assert _normalize_lang("golang") == "go"
    assert _normalize_lang("Python") == "python"
    assert _normalize_lang("") == ""
    assert _normalize_lang("rust") == "rust"


def test_parse_date_formats():
    assert _parse_date("2023-05-01").year == 2023
    assert _parse_date("2022/11").month == 11
    assert _parse_date("Jan 2020").year == 2020
    assert _parse_date("2019").year == 2019
    assert _parse_date("Present") is None
    assert _parse_date("current") is None
    assert _parse_date("") is None
    assert _parse_date(None) is None
    assert _parse_date("garbage") is None


def test_months_between():
    from datetime import datetime
    assert _months_between(datetime(2023, 1, 1), datetime(2023, 6, 1)) == 5
    assert _months_between(datetime(2022, 1, 1), datetime(2024, 1, 1)) == 24


# ---------------------------------------------------------------------------
# GitHubCommitValidator
# ---------------------------------------------------------------------------

def test_github_validator_skips_when_no_github_source():
    p = _profile(sources_used=["resume"])
    out = _run(GitHubCommitValidator().validate(p))
    assert out == []


def test_github_validator_skips_when_no_languages_in_profile():
    p = _profile(sources_used=["github"], experience=[{"title": "Dev"}])
    out = _run(GitHubCommitValidator().validate(p))
    assert out == []


def test_github_validator_verifies_matching_language():
    skill = CandidateSkill(
        name="Python",
        provenance=[SkillProvenance(source="github_user")],
    )
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[{"source": "github", "languages": ["Python", "JavaScript"]}],
    )
    out = _run(GitHubCommitValidator().validate(p))
    assert len(out) == 1
    assert out[0].status == "verified"
    assert "Python" in out[0].claim


def test_github_validator_conflicts_on_missing_language():
    skill = CandidateSkill(
        name="Rust",
        provenance=[SkillProvenance(source="github_user")],
    )
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[{"source": "github", "languages": ["Python"]}],
    )
    out = _run(GitHubCommitValidator().validate(p))
    assert len(out) == 1
    assert out[0].status == "conflicted"


def test_github_validator_ignores_non_github_skills():
    skill = CandidateSkill(
        name="Excel",
        provenance=[SkillProvenance(source="resume")],
    )
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[{"source": "github", "languages": ["Python"]}],
    )
    out = _run(GitHubCommitValidator().validate(p))
    assert out == []  # skill not backed by github → skipped


def test_github_validator_normalizes_aliases():
    skill = CandidateSkill(
        name="Node.js",
        provenance=[SkillProvenance(source="github_user")],
    )
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[{"source": "github", "languages": ["JavaScript"]}],
    )
    out = _run(GitHubCommitValidator().validate(p))
    assert len(out) == 1
    assert out[0].status == "verified"


def test_github_validator_uses_top_level_github_languages_key():
    skill = CandidateSkill(
        name="Go",
        provenance=[SkillProvenance(source="github_user")],
    )
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[{"github_languages": ["Go", "Rust"]}],
    )
    out = _run(GitHubCommitValidator().validate(p))
    assert len(out) == 1
    assert out[0].status == "verified"


# ---------------------------------------------------------------------------
# DateConsistencyValidator
# ---------------------------------------------------------------------------

def test_date_validator_empty_experience_returns_empty():
    out = _run(DateConsistencyValidator().validate(_profile()))
    assert out == []


def test_date_validator_clean_timeline_emits_verified():
    p = _profile(experience=[
        {"title": "Eng", "start_date": "2020-01-01", "end_date": "2022-01-01"},
        {"title": "Sr Eng", "start_date": "2022-02-01", "end_date": "2024-01-01"},
    ])
    out = _run(DateConsistencyValidator().validate(p))
    assert len(out) == 1
    assert out[0].status == "verified"
    assert "consistent" in out[0].claim.lower()


def test_date_validator_flags_overlap():
    p = _profile(experience=[
        {"title": "RoleA", "start_date": "2020-01-01", "end_date": "2023-01-01"},
        {"title": "RoleB", "start_date": "2022-01-01", "end_date": "2024-01-01"},
    ])
    out = _run(DateConsistencyValidator().validate(p))
    overlaps = [c for c in out if c.status == "conflicted"]
    assert len(overlaps) == 1
    assert "Overlapping" in overlaps[0].claim


def test_date_validator_flags_large_gap():
    p = _profile(experience=[
        {"title": "RoleA", "start_date": "2018-01-01", "end_date": "2019-01-01"},
        {"title": "RoleB", "start_date": "2021-01-01", "end_date": "2023-01-01"},
    ])
    out = _run(DateConsistencyValidator().validate(p))
    gaps = [c for c in out if "gap" in c.claim.lower()]
    assert len(gaps) == 1
    assert gaps[0].status == "unverified"


def test_date_validator_ignores_small_gap():
    p = _profile(experience=[
        {"title": "RoleA", "start_date": "2020-01-01", "end_date": "2020-06-01"},
        {"title": "RoleB", "start_date": "2020-09-01", "end_date": "2022-01-01"},
    ])
    out = _run(DateConsistencyValidator().validate(p))
    # 3-month gap is below threshold → no gap claim
    assert all("gap" not in c.claim.lower() for c in out)


def test_date_validator_skips_unparseable_entries():
    p = _profile(experience=[
        {"title": "RoleA", "start_date": "garbage"},
        {"title": "RoleB", "start_date": "2020-01-01", "end_date": "2022-01-01"},
    ])
    out = _run(DateConsistencyValidator().validate(p))
    # Only one parseable entry → still emits the verified summary
    assert len(out) == 1
    assert out[0].status == "verified"


# ---------------------------------------------------------------------------
# CompanyExistsValidator
# ---------------------------------------------------------------------------

def test_company_validator_no_companies_returns_empty():
    out = _run(CompanyExistsValidator().validate(_profile()))
    assert out == []


def test_company_validator_verifies_known_company():
    client = _FakeClient({"stripe": _FakeResp(200, {
        "search": [{"id": "Q123", "label": "Stripe"}],
    })})
    p = _profile(experience=[{"company": "Stripe"}])
    out = _run(CompanyExistsValidator(http_client=client).validate(p))
    assert len(out) == 1
    assert out[0].status == "verified"
    assert "Q123" in out[0].detail


def test_company_validator_unverified_when_no_match():
    client = _FakeClient({"madeup": _FakeResp(200, {"search": []})})
    p = _profile(experience=[{"company": "MadeUp Co"}])
    out = _run(CompanyExistsValidator(http_client=client).validate(p))
    assert len(out) == 1
    assert out[0].status == "unverified"
    assert "no wikidata match" in out[0].detail


def test_company_validator_unverified_on_http_error():
    client = _FakeClient({"acme": _FakeResp(500, {})})
    p = _profile(experience=[{"company": "Acme"}])
    out = _run(CompanyExistsValidator(http_client=client).validate(p))
    assert len(out) == 1
    assert out[0].status == "unverified"
    assert "HTTP 500" in out[0].detail


def test_company_validator_unverified_on_network_exception():
    client = _FakeClient({"acme": RuntimeError("boom")})
    p = _profile(experience=[{"company": "Acme"}])
    out = _run(CompanyExistsValidator(http_client=client).validate(p))
    assert len(out) == 1
    assert out[0].status == "unverified"
    assert "RuntimeError" in out[0].detail


def test_company_validator_dedupes_companies():
    client = _FakeClient({"stripe": _FakeResp(200, {
        "search": [{"id": "Q1", "label": "Stripe"}],
    })})
    p = _profile(experience=[
        {"company": "Stripe"},
        {"company": "stripe"},  # case-different dup
        {"company": "STRIPE"},
    ])
    out = _run(CompanyExistsValidator(http_client=client).validate(p))
    assert len(out) == 1
    assert len(client.calls) == 1


def test_company_validator_skips_blank_company_field():
    client = _FakeClient({})
    p = _profile(experience=[{"company": ""}, {"title": "no company key"}])
    out = _run(CompanyExistsValidator(http_client=client).validate(p))
    assert out == []
    assert client.calls == []


# ---------------------------------------------------------------------------
# ValidationSwarm orchestration
# ---------------------------------------------------------------------------

def test_swarm_aggregates_three_validators():
    skill = CandidateSkill(
        name="Python",
        provenance=[SkillProvenance(source="github_user")],
    )
    client = _FakeClient({"acme": _FakeResp(200, {
        "search": [{"id": "Q9", "label": "Acme"}],
    })})
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[
            {"source": "github", "languages": ["Python"]},
            {"company": "Acme", "title": "Eng",
             "start_date": "2020-01-01", "end_date": "2023-01-01"},
        ],
    )
    swarm = ValidationSwarm(
        company_validator=CompanyExistsValidator(http_client=client),
    )
    report = _run(swarm.validate(p))
    statuses = {c.validator for c in report.claims}
    assert "github_commits" in statuses
    assert "date_consistency" in statuses
    assert "company_exists" in statuses
    assert report.verified_count >= 2


def test_swarm_counts_conflicted_claims():
    skill = CandidateSkill(
        name="Rust",
        provenance=[SkillProvenance(source="github_user")],
    )
    p = _profile(
        skills=[skill],
        sources_used=["github"],
        experience=[
            {"source": "github", "languages": ["Python"]},  # rust missing → conflict
            {"title": "RoleA", "start_date": "2020-01-01", "end_date": "2023-01-01"},
            {"title": "RoleB", "start_date": "2022-01-01", "end_date": "2024-01-01"},  # overlap
        ],
    )
    # Disable network validator entirely.
    class _NoOpCompany:
        name = "company_exists"
        async def validate(self, _profile):
            return []
    swarm = ValidationSwarm(company_validator=_NoOpCompany())
    report = _run(swarm.validate(p))
    assert report.conflicted_count == 2  # rust conflict + overlap


def test_swarm_validator_failure_does_not_propagate():
    class _BoomValidator:
        name = "boom"
        async def validate(self, _profile):
            raise RuntimeError("unexpected")

    p = _profile(experience=[{"title": "x", "start_date": "2020-01-01", "end_date": "2022-01-01"}])
    swarm = ValidationSwarm(
        github_validator=_BoomValidator(),
        company_validator=_BoomValidator(),
    )
    report = _run(swarm.validate(p))
    # date validator still ran → at least the verified summary
    assert any(c.validator == "date_consistency" for c in report.claims)


def test_swarm_handles_none_profile():
    swarm = ValidationSwarm()
    report = _run(swarm.validate(None))
    assert report.claims == []
    assert report.verified_count == 0
    assert report.conflicted_count == 0


def test_swarm_empty_profile_returns_empty_report():
    swarm = ValidationSwarm(
        company_validator=CompanyExistsValidator(http_client=_FakeClient({})),
    )
    report = _run(swarm.validate(_profile()))
    assert report.verified_count == 0
    assert report.conflicted_count == 0


def test_swarm_report_carries_creator_tag():
    swarm = ValidationSwarm(
        company_validator=CompanyExistsValidator(http_client=_FakeClient({})),
    )
    report = _run(swarm.validate(_profile()))
    assert report.created_by_agent == "atlas.validation_swarm"
