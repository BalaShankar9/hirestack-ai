"""Unit tests for ATLAS ArchetypeGenerator."""
from __future__ import annotations

import asyncio

import pytest

from ai_engine.agents.artifact_contracts import Archetype
from ai_engine.agents.sub_agents.atlas import dynamic_archetypes
from ai_engine.agents.sub_agents.atlas.dynamic_archetypes import (
    ArchetypeGenerator,
    _coerce_int,
    _coerce_str_list,
    _parse_archetypes,
    reset_cache,
)


_run = asyncio.run


@pytest.fixture(autouse=True)
def _clear_cache():
    reset_cache()
    yield
    reset_cache()


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [(5, 5), ("7", 7), ("not-a-number", 0), (None, 0), (3.7, 3)],
)
def test_coerce_int(raw, expected):
    assert _coerce_int(raw) == expected


def test_coerce_str_list_filters_empty_and_none():
    assert _coerce_str_list(["a", "", "  ", None, "b"]) == ["a", "b"]
    assert _coerce_str_list("not a list") == []
    assert _coerce_str_list(None) == []


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def _good_payload():
    return {
        "archetypes": [
            {
                "name": "Big-Tech Senior Eng",
                "must_have_skills": ["Python", "Distributed Systems"],
                "nice_to_have_skills": ["Kubernetes"],
                "years_min": 7,
                "years_max": 12,
                "cultural_signals": ["scale-driven"],
                "rationale": "Scaled services to 100M users.",
            },
            {
                "name": "Scrappy Startup Builder",
                "must_have_skills": ["Python", "Shipping fast"],
                "years_min": 4,
                "years_max": 8,
                "rationale": "Owns product end-to-end.",
            },
            {
                "name": "Domain Expert (FinTech)",
                "must_have_skills": ["Compliance", "Payments"],
                "years_min": 8,
                "years_max": 15,
                "rationale": "Regulatory depth.",
            },
        ]
    }


def test_parse_archetypes_happy():
    out = _parse_archetypes(_good_payload())
    assert len(out) == 3
    assert all(isinstance(a, Archetype) for a in out)
    assert out[0].name == "Big-Tech Senior Eng"
    assert out[0].nice_to_have_skills == ["Kubernetes"]
    assert out[0].salary_band == {}  # placeholder


def test_parse_archetypes_clamps_to_three():
    payload = {"archetypes": [{"name": f"a{i}", "rationale": "r"} for i in range(10)]}
    out = _parse_archetypes(payload)
    assert len(out) == 3


def test_parse_archetypes_skips_missing_name_and_non_dict():
    payload = {"archetypes": [
        {"name": "", "rationale": "r"},
        "not a dict",
        {"name": "Ok", "rationale": "r"},
        {"rationale": "no name"},
    ]}
    out = _parse_archetypes(payload)
    assert len(out) == 1
    assert out[0].name == "Ok"


def test_parse_archetypes_fixes_inverted_year_range():
    payload = {"archetypes": [
        {"name": "X", "rationale": "r", "years_min": 10, "years_max": 5}
    ]}
    out = _parse_archetypes(payload)
    assert out[0].years_min == 10
    assert out[0].years_max == 10  # corrected


def test_parse_archetypes_handles_garbage():
    assert _parse_archetypes(None) == []
    assert _parse_archetypes({"archetypes": "not a list"}) == []
    assert _parse_archetypes("string") == []


# ---------------------------------------------------------------------------
# ArchetypeGenerator.generate
# ---------------------------------------------------------------------------

def test_generator_requires_client():
    with pytest.raises(ValueError):
        ArchetypeGenerator(ai_client=None)


def test_generate_empty_jd_returns_empty():
    class _Boom:
        async def complete_json(self, **_kw):
            raise AssertionError("must not call LLM for empty JD")

    g = ArchetypeGenerator(ai_client=_Boom())
    assert _run(g.generate(job_description="")) == []
    assert _run(g.generate(job_description="   \n  ")) == []


def test_generate_happy_returns_three_archetypes():
    class _StubClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return _good_payload()

    client = _StubClient()
    g = ArchetypeGenerator(ai_client=client)
    out = _run(g.generate(job_description="Senior backend engineer @ Stripe"))
    assert client.calls == 1
    assert len(out) == 3
    assert out[0].name == "Big-Tech Senior Eng"


def test_generate_uses_cache_on_repeat():
    class _CountingClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return _good_payload()

    client = _CountingClient()
    g = ArchetypeGenerator(ai_client=client)
    _run(g.generate(job_description="Senior backend engineer @ Stripe",
                    role_target="senior_backend"))
    _run(g.generate(job_description="Senior backend engineer @ Stripe",
                    role_target="senior_backend"))
    assert client.calls == 1  # cache hit on second call


def test_generate_use_cache_false_bypasses_cache():
    class _CountingClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return _good_payload()

    client = _CountingClient()
    g = ArchetypeGenerator(ai_client=client)
    _run(g.generate(job_description="x", role_target="r"))
    _run(g.generate(job_description="x", role_target="r", use_cache=False))
    assert client.calls == 2


def test_generate_different_jds_get_different_cache_keys():
    class _CountingClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return _good_payload()

    client = _CountingClient()
    g = ArchetypeGenerator(ai_client=client)
    _run(g.generate(job_description="JD A"))
    _run(g.generate(job_description="JD B"))
    assert client.calls == 2


def test_generate_different_role_targets_get_different_cache_keys():
    class _CountingClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return _good_payload()

    client = _CountingClient()
    g = ArchetypeGenerator(ai_client=client)
    _run(g.generate(job_description="JD", role_target="senior"))
    _run(g.generate(job_description="JD", role_target="staff"))
    assert client.calls == 2


def test_generate_llm_failure_returns_empty():
    class _BoomClient:
        async def complete_json(self, **_kw):
            raise RuntimeError("boom")

    g = ArchetypeGenerator(ai_client=_BoomClient())
    out = _run(g.generate(job_description="anything"))
    assert out == []


def test_generate_partial_response_not_cached():
    """If LLM returns < 3 archetypes, return them but do NOT cache."""
    class _PartialClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return {"archetypes": [{"name": "Only One", "rationale": "r"}]}

    client = _PartialClient()
    g = ArchetypeGenerator(ai_client=client)
    out1 = _run(g.generate(job_description="JD"))
    out2 = _run(g.generate(job_description="JD"))
    assert len(out1) == 1
    assert client.calls == 2  # second call NOT served from cache


def test_generate_cache_ttl_expires(monkeypatch):
    """When TTL expires, cache should miss and re-call LLM."""
    class _CountingClient:
        def __init__(self):
            self.calls = 0

        async def complete_json(self, **_kw):
            self.calls += 1
            return _good_payload()

    client = _CountingClient()
    g = ArchetypeGenerator(ai_client=client)
    _run(g.generate(job_description="JD"))

    # Fast-forward time past TTL.
    real_time = dynamic_archetypes.time
    fake_now = real_time.time() + dynamic_archetypes._CACHE_TTL_SECONDS + 1
    monkeypatch.setattr(dynamic_archetypes.time, "time", lambda: fake_now)

    _run(g.generate(job_description="JD"))
    assert client.calls == 2


def test_generate_passes_job_context_into_prompt():
    captured = {}

    class _CapturingClient:
        async def complete_json(self, **kw):
            captured.update(kw)
            return _good_payload()

    g = ArchetypeGenerator(ai_client=_CapturingClient())
    _run(g.generate(
        job_description="We need a Rust expert",
        role_target="staff_engineer",
        company_industry="fintech",
        company_name="Stripe",
    ))
    prompt = captured["prompt"]
    assert "Rust expert" in prompt
    assert "staff_engineer" in prompt
    assert "fintech" in prompt
    assert "Stripe" in prompt
    assert captured["temperature"] == 0.4
    assert captured["max_tokens"] == 2048
