"""ATLAS Slice 3.2 — RoleProfilerChain ValidationSwarm wiring tests.

Verifies that ATLAS_VALIDATION_SWARM_ENABLED env-flag gating is
strict opt-in, that `validation_report` is appended additively to
the existing parsed result without disturbing any other field, and
that swarm failure degrades gracefully.
"""
from __future__ import annotations

import asyncio
import copy
from typing import Any, Dict
from unittest.mock import MagicMock

import pytest

from ai_engine.chains import role_profiler as rp_mod
from ai_engine.chains.role_profiler import RoleProfilerChain, _atlas_validation_enabled


def _run(coro):
    return asyncio.run(coro)


class _StubAIClient:
    """Returns a canned parsed-resume dict, no real LLM call."""

    def __init__(self, payload: Dict[str, Any]):
        self._payload = payload
        self.calls = 0

    async def complete_json(self, **_kw):
        self.calls += 1
        # Deep-copy so per-test mutations don't bleed across cases.
        return copy.deepcopy(self._payload)


_BASIC_PAYLOAD: Dict[str, Any] = {
    "name": "Jane Doe",
    "title": "Senior Engineer",
    "summary": "10y exp.",
    "contact_info": {"email": "jane@example.com"},
    "skills": [
        {"name": "Python", "level": "expert"},
        {"name": "Go", "level": "advanced"},
    ],
    "experience": [
        {
            "company": "Acme",
            "title": "Eng",
            "start_date": "2020-01-01",
            "end_date": "2022-01-01",
        },
        {
            "company": "Beta",
            "title": "Sr Eng",
            "start_date": "2022-02-01",
            "end_date": "Present",
        },
    ],
    "education": [],
    "certifications": [],
    "projects": [],
    "languages": [],
    "achievements": [],
}


# ---------------------------------------------------------------------------
# Env flag helper
# ---------------------------------------------------------------------------

def test_validation_flag_default_off(monkeypatch):
    monkeypatch.delenv("ATLAS_VALIDATION_SWARM_ENABLED", raising=False)
    assert _atlas_validation_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "TRUE", "yes", "on", " On "])
def test_validation_flag_truthy(monkeypatch, val):
    monkeypatch.setenv("ATLAS_VALIDATION_SWARM_ENABLED", val)
    assert _atlas_validation_enabled() is True


@pytest.mark.parametrize("val", ["0", "false", "no", "off", "", "maybe"])
def test_validation_flag_falsy(monkeypatch, val):
    monkeypatch.setenv("ATLAS_VALIDATION_SWARM_ENABLED", val)
    assert _atlas_validation_enabled() is False


# ---------------------------------------------------------------------------
# Default-off: parse_resume must not run swarm
# ---------------------------------------------------------------------------

def test_parse_resume_default_off_no_validation_report(monkeypatch):
    monkeypatch.delenv("ATLAS_VALIDATION_SWARM_ENABLED", raising=False)
    chain = RoleProfilerChain(_StubAIClient(_BASIC_PAYLOAD))
    out = _run(chain.parse_resume("dummy resume"))
    assert "validation_report" not in out
    # All canonical fields preserved
    assert out["name"] == "Jane Doe"
    assert len(out["skills"]) == 2
    assert "parse_confidence" in out


# ---------------------------------------------------------------------------
# Flag on: validation_report appears additively
# ---------------------------------------------------------------------------

def test_parse_resume_flag_on_adds_validation_report(monkeypatch):
    monkeypatch.setenv("ATLAS_VALIDATION_SWARM_ENABLED", "true")

    # Stub out the lazy-imported ValidationSwarm so we don't make
    # real Wikidata calls. The wiring code calls
    # `ValidationSwarm()` and then `await swarm.validate(profile)`.
    captured = {}

    class _StubReport:
        def model_dump(self):
            return {
                "claims": [{"claim": "x", "validator": "stub", "status": "verified", "detail": ""}],
                "verified_count": 1,
                "conflicted_count": 0,
                "version": "1.0.0",
                "created_by_agent": "atlas.validation_swarm",
            }

    class _StubSwarm:
        def __init__(self):
            captured["constructed"] = True

        async def validate(self, profile):
            captured["profile"] = profile
            return _StubReport()

    import ai_engine.agents.sub_agents.atlas.validation_swarm as vs_mod
    monkeypatch.setattr(vs_mod, "ValidationSwarm", _StubSwarm)

    chain = RoleProfilerChain(_StubAIClient(_BASIC_PAYLOAD))
    out = _run(chain.parse_resume("dummy"))

    assert captured.get("constructed") is True
    profile = captured["profile"]
    # The built profile carries the parsed name + experience entries
    assert profile.candidate_name == "Jane Doe"
    assert len(profile.experience) == 2
    assert "resume" in profile.sources_used
    # All skills carry resume provenance
    assert len(profile.skills) == 2
    for s in profile.skills:
        assert any(p.source == "resume" for p in s.provenance)

    # Report appears in the output dict, additively
    assert "validation_report" in out
    rep = out["validation_report"]
    assert rep["verified_count"] == 1
    assert rep["conflicted_count"] == 0
    # Existing fields untouched
    assert out["name"] == "Jane Doe"
    assert "parse_confidence" in out


def test_parse_resume_flag_on_swarm_exception_does_not_break(monkeypatch):
    monkeypatch.setenv("ATLAS_VALIDATION_SWARM_ENABLED", "1")

    class _BoomSwarm:
        def __init__(self):
            pass

        async def validate(self, _profile):
            raise RuntimeError("network down")

    import ai_engine.agents.sub_agents.atlas.validation_swarm as vs_mod
    monkeypatch.setattr(vs_mod, "ValidationSwarm", _BoomSwarm)

    chain = RoleProfilerChain(_StubAIClient(_BASIC_PAYLOAD))
    out = _run(chain.parse_resume("dummy"))

    # Swarm raised → no validation_report key, but parse still succeeded
    assert "validation_report" not in out
    assert out["name"] == "Jane Doe"
    assert "parse_confidence" in out


def test_parse_resume_flag_on_skips_invalid_skill_entries(monkeypatch):
    monkeypatch.setenv("ATLAS_VALIDATION_SWARM_ENABLED", "1")

    captured = {}

    class _StubSwarm:
        def __init__(self):
            pass

        async def validate(self, profile):
            captured["profile"] = profile
            class _R:
                def model_dump(self):
                    return {"claims": [], "verified_count": 0, "conflicted_count": 0}
            return _R()

    import ai_engine.agents.sub_agents.atlas.validation_swarm as vs_mod
    monkeypatch.setattr(vs_mod, "ValidationSwarm", _StubSwarm)

    payload = dict(_BASIC_PAYLOAD)
    payload["skills"] = [
        {"name": "Python"},
        {"name": ""},  # empty name → skipped
        {"foo": "bar"},  # missing name → skipped
        "not-a-dict",  # not a dict → skipped
    ]
    chain = RoleProfilerChain(_StubAIClient(payload))
    _run(chain.parse_resume("dummy"))

    profile = captured["profile"]
    # Only "Python" survives
    assert len(profile.skills) == 1
    assert profile.skills[0].name == "Python"
