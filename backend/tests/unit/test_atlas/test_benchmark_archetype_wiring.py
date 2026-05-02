"""Tests for ATLAS archetype wiring into BenchmarkBuilderChain."""
from __future__ import annotations

import asyncio

import pytest

from ai_engine.chains import benchmark_builder
from ai_engine.chains.benchmark_builder import BenchmarkBuilderChain


_run = asyncio.run


class _StubAIClient:
    """Minimal AIClient stub. Routes by call type."""

    def __init__(self, *, archetype_payload=None, ideal_profile_payload=None,
                 portfolio_payload=None, case_studies_payload=None,
                 action_plan_payload=None):
        self._archetype = archetype_payload
        self._ideal = ideal_profile_payload
        self._portfolio = portfolio_payload or {"projects": []}
        self._cases = case_studies_payload or {"case_studies": []}
        self._plan = action_plan_payload or {"action_plan": {}}
        self.calls = []

    async def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        sysmsg = (kwargs.get("system") or "").lower()
        prompt = (kwargs.get("prompt") or "").lower()
        if "exactly three distinct candidate" in sysmsg:
            return self._archetype or {}
        if "ideal candidate profile" in prompt or "ideal_profile" in prompt:
            return self._ideal or {}
        if "portfolio" in prompt:
            return self._portfolio
        if "case stud" in prompt:
            return self._cases
        if "action plan" in prompt or "action_plan" in prompt:
            return self._plan
        return {}

    async def complete(self, **kwargs):
        self.calls.append(kwargs)
        return "stub-text"


def _ideal_profile_payload():
    return {
        "ideal_profile": {"name": "X", "title": "Senior", "years_experience": 7,
                          "summary": "s"},
        "ideal_skills": [], "ideal_experience": [], "ideal_education": [],
        "ideal_certifications": [], "soft_skills": [], "industry_knowledge": [],
        "scoring_weights": {},
    }


def _benchmark_doc_payloads():
    """Deprecated — kept as no-op for backwards compatibility."""
    return []


def test_archetypes_disabled_by_default(monkeypatch):
    monkeypatch.delenv("ATLAS_ARCHETYPES_ENABLED", raising=False)
    client = _StubAIClient(ideal_profile_payload=_ideal_profile_payload())
    chain = BenchmarkBuilderChain(client)

    out = _run(chain.build_complete_benchmark(
        job_title="Eng", company="Acme", job_description="desc",
    ))
    assert out["atlas_archetypes"] == []
    # No archetype-shaped LLM call
    for call in client.calls:
        assert "exactly three distinct candidate" not in (call.get("system") or "").lower()


def test_archetypes_enabled_calls_generator(monkeypatch):
    monkeypatch.setenv("ATLAS_ARCHETYPES_ENABLED", "1")

    archetype_payload = {
        "archetypes": [
            {"name": "A", "rationale": "r", "must_have_skills": ["py"],
             "years_min": 5, "years_max": 8},
            {"name": "B", "rationale": "r", "years_min": 3, "years_max": 6},
            {"name": "C", "rationale": "r", "years_min": 8, "years_max": 12},
        ]
    }
    client = _StubAIClient(
        archetype_payload=archetype_payload,
        ideal_profile_payload=_ideal_profile_payload(),
    )
    chain = BenchmarkBuilderChain(client)

    from ai_engine.agents.sub_agents.atlas import dynamic_archetypes
    dynamic_archetypes.reset_cache()

    out = _run(chain.build_complete_benchmark(
        job_title="Senior Eng", company="Acme",
        job_description="Do the thing",
        company_info={"industry": "fintech"},
    ))
    assert len(out["atlas_archetypes"]) == 3
    assert out["atlas_archetypes"][0]["name"] == "A"
    for key in ("ideal_profile", "ideal_skills", "ideal_cv",
                "ideal_cover_letter", "ideal_portfolio",
                "ideal_case_studies", "ideal_action_plan"):
        assert key in out


def test_archetype_failure_does_not_break_benchmark(monkeypatch):
    monkeypatch.setenv("ATLAS_ARCHETYPES_ENABLED", "1")

    class _ArchetypeFailingClient(_StubAIClient):
        async def complete_json(self, **kwargs):
            sysmsg = (kwargs.get("system") or "").lower()
            if "exactly three distinct candidate" in sysmsg:
                self.calls.append(kwargs)
                raise RuntimeError("LLM down")
            return await super().complete_json(**kwargs)

    client = _ArchetypeFailingClient(ideal_profile_payload=_ideal_profile_payload())
    chain = BenchmarkBuilderChain(client)

    from ai_engine.agents.sub_agents.atlas import dynamic_archetypes
    dynamic_archetypes.reset_cache()

    out = _run(chain.build_complete_benchmark(
        job_title="Eng", company="Acme", job_description="desc",
    ))
    assert out["atlas_archetypes"] == []
    assert out["ideal_profile"] is not None


def test_helper_env_flag_truthiness(monkeypatch):
    for v in ("1", "true", "TRUE", "yes", "on", " 1 "):
        monkeypatch.setenv("ATLAS_ARCHETYPES_ENABLED", v)
        assert benchmark_builder._atlas_archetypes_enabled() is True
    for v in ("", "0", "false", "no", "off", "maybe"):
        monkeypatch.setenv("ATLAS_ARCHETYPES_ENABLED", v)
        assert benchmark_builder._atlas_archetypes_enabled() is False
