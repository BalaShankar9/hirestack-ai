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


# ---------------------------------------------------------------------------
# Salary band injection (Slice 2.4)
# ---------------------------------------------------------------------------

class _StubProviderResult:
    def __init__(self, *, success, raw=None):
        self.success = success
        self.raw = raw or {}


class _StubSalaryProvider:
    def __init__(self, result):
        self._result = result
        self.calls = []

    async def fetch(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


def _stub_client_with_payload():
    class _C:
        async def complete_json(self, **_kw):
            return _good_payload()
    return _C()


def test_salary_band_default_off_no_provider_no_band(monkeypatch):
    monkeypatch.delenv("RECON_LEVELS_PROVIDER", raising=False)
    g = ArchetypeGenerator(ai_client=_stub_client_with_payload())
    out = _run(g.generate(
        job_description="JD", company_name="Stripe", role_target="senior_eng",
    ))
    assert len(out) == 3
    for a in out:
        assert a.salary_band == {}


def test_salary_band_injected_when_provider_supplied():
    band = {"p25": 160000, "p50": 185000, "p75": 220000}
    provider = _StubSalaryProvider(_StubProviderResult(
        success=True, raw={"salary_band": band},
    ))
    g = ArchetypeGenerator(
        ai_client=_stub_client_with_payload(),
        salary_provider=provider,
    )
    out = _run(g.generate(
        job_description="JD", company_name="Stripe", role_target="senior_eng",
    ))
    assert len(out) == 3
    assert all(a.salary_band == band for a in out)
    # Single fetch (shared across all 3 archetypes — same company+role)
    assert len(provider.calls) == 1
    assert provider.calls[0]["company"] == "Stripe"
    assert provider.calls[0]["role"] == "senior_eng"


def test_salary_band_per_archetype_isolation():
    """Each archetype should have its own dict instance (no shared mutation)."""
    band = {"p50": 200000}
    provider = _StubSalaryProvider(_StubProviderResult(
        success=True, raw={"salary_band": band},
    ))
    g = ArchetypeGenerator(
        ai_client=_stub_client_with_payload(),
        salary_provider=provider,
    )
    out = _run(g.generate(job_description="JD", company_name="Acme"))
    out[0].salary_band["mutated"] = 1
    assert "mutated" not in out[1].salary_band
    assert "mutated" not in out[2].salary_band


def test_salary_band_provider_failure_keeps_band_empty():
    provider = _StubSalaryProvider(_StubProviderResult(success=False))
    g = ArchetypeGenerator(
        ai_client=_stub_client_with_payload(),
        salary_provider=provider,
    )
    out = _run(g.generate(job_description="JD", company_name="Acme"))
    assert all(a.salary_band == {} for a in out)


def test_salary_band_provider_exception_keeps_band_empty():
    class _BoomProvider:
        async def fetch(self, **_kw):
            raise RuntimeError("network")

    g = ArchetypeGenerator(
        ai_client=_stub_client_with_payload(),
        salary_provider=_BoomProvider(),
    )
    out = _run(g.generate(job_description="JD", company_name="Acme"))
    assert all(a.salary_band == {} for a in out)


def test_salary_band_skipped_when_no_company_name():
    provider = _StubSalaryProvider(_StubProviderResult(
        success=True, raw={"salary_band": {"p50": 100000}},
    ))
    g = ArchetypeGenerator(
        ai_client=_stub_client_with_payload(),
        salary_provider=provider,
    )
    out = _run(g.generate(job_description="JD", company_name=""))
    assert all(a.salary_band == {} for a in out)
    assert provider.calls == []  # never even attempted


def test_salary_band_env_flag_lazy_imports_provider(monkeypatch):
    """RECON_LEVELS_PROVIDER=real should attempt to import LevelsFYIProvider."""
    monkeypatch.setenv("RECON_LEVELS_PROVIDER", "real")

    captured = {}

    class _FakeLevels:
        def __init__(self, *a, **kw):
            captured["constructed"] = True

        async def fetch(self, **kw):
            captured["fetch_called"] = kw
            return _StubProviderResult(success=True, raw={"salary_band": {"p50": 999}})

    # Patch the module that ArchetypeGenerator imports lazily.
    import ai_engine.agents.sub_agents.atlas.sources.levels_fyi as lv_mod
    monkeypatch.setattr(lv_mod, "LevelsFYIProvider", _FakeLevels)

    g = ArchetypeGenerator(ai_client=_stub_client_with_payload())
    out = _run(g.generate(job_description="JD", company_name="Acme"))
    assert captured.get("constructed") is True
    assert captured.get("fetch_called", {}).get("company") == "Acme"
    assert all(a.salary_band == {"p50": 999} for a in out)
