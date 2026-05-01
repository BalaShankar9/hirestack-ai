"""S18 — Recon Swarm v2 unit tests."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from ai_engine.agents.sub_agents.recon_swarm import (
    ApplicationMapper,
    CompanyIntelV2,
    IntelFusion,
    ProviderResult,
    ReconSwarmCoordinator,
    ReconSwarmRequest,
    SECEdgarProvider,
    StubBuiltWithProvider,
    StubCrunchbaseProvider,
    StubGitHubProvider,
    StubGlassdoorProvider,
    StubGoogleNewsProvider,
    StubLinkedInProvider,
    StubPatentProvider,
    StubProductHuntProvider,
    StubSECProvider,
    StubTwitterProvider,
    build_recon_swarm_tools,
    detect_recon_swarm_intent,
)
from ai_engine.agents.sub_agents.recon_swarm.cache import _MemoryCache
from ai_engine.agents.sub_agents.recon_swarm.providers import (
    StubWebsiteCrawlerProvider,
    default_layer1_providers,
    default_layer2_providers,
)


# ─── intent ────────────────────────────────────────────────────────

def test_intent_matches_phrases():
    assert detect_recon_swarm_intent("run the recon swarm on Stripe")
    assert detect_recon_swarm_intent("do a deep recon on Anthropic")
    assert detect_recon_swarm_intent("build a company dossier for OpenAI")


def test_intent_misses_unrelated():
    assert detect_recon_swarm_intent("write a cover letter") is None
    assert detect_recon_swarm_intent("") is None


# ─── stub providers are deterministic ──────────────────────────────

@pytest.mark.asyncio
async def test_stub_crunchbase_deterministic():
    p = StubCrunchbaseProvider()
    a = await p.fetch(company="Acme")
    b = await p.fetch(company="Acme")
    assert a.success and b.success
    assert a.raw["last_round"] == b.raw["last_round"]
    assert a.raw["total_funding_usd"] == b.raw["total_funding_usd"]
    assert a.layer == 1


@pytest.mark.asyncio
async def test_all_layer1_stubs_succeed():
    providers = [
        StubCrunchbaseProvider(), StubLinkedInProvider(),
        StubBuiltWithProvider(), StubGitHubProvider(),
        StubGoogleNewsProvider(),
    ]
    results = await asyncio.gather(*[p.fetch(company="Acme") for p in providers])
    assert all(r.success for r in results)
    assert all(r.layer == 1 for r in results)


@pytest.mark.asyncio
async def test_layer2_sec_returns_public_payload_only_when_flagged():
    p = StubSECProvider()
    private = await p.fetch(company="Acme")
    public = await p.fetch(company="Acme", is_public=True)
    assert private.raw == {"is_public": False}
    assert public.raw["is_public"] is True
    assert "ticker" in public.raw and public.raw["sec_revenue_usd"] > 0


@pytest.mark.asyncio
async def test_website_crawler_falls_back_to_canned_text():
    p = StubWebsiteCrawlerProvider()
    r = await p.fetch(company="Acme", website="", allow_network=False)
    assert r.success
    assert "Acme" in r.raw["raw_about_text"]
    assert "ownership" in r.raw["values"]


@pytest.mark.asyncio
async def test_glassdoor_and_twitter_stubs_shape():
    g = await StubGlassdoorProvider().fetch(company="Acme")
    t = await StubTwitterProvider().fetch(company="Acme")
    assert isinstance(g.raw["glassdoor_rating"], float)
    assert g.raw["glassdoor_themes"]
    assert t.raw["twitter_handle"].startswith("@")


# ─── intel fusion ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fusion_merges_scalar_with_high_confidence_when_two_agree():
    fusion = IntelFusion()
    results = [
        ProviderResult(provider="a", layer=1, success=True,
                       raw={"headcount": 200}),
        ProviderResult(provider="b", layer=1, success=True,
                       raw={"headcount": 200}),
        ProviderResult(provider="c", layer=1, success=True,
                       raw={"headcount": 999}),
    ]
    intel = await fusion.fuse("Acme", results)
    assert intel.headcount.value == 200
    assert intel.headcount.confidence == "high"
    assert {"a", "b"} <= set(intel.headcount.sources)


@pytest.mark.asyncio
async def test_fusion_dedupes_list_items_and_tracks_sources():
    fusion = IntelFusion()
    results = [
        ProviderResult(provider="a", layer=1, success=True,
                       raw={"tech_stack": ["React", "Python"]}),
        ProviderResult(provider="b", layer=1, success=True,
                       raw={"tech_stack": ["python", "Postgres"]}),
    ]
    intel = await fusion.fuse("Acme", results)
    stack = intel.tech_stack.value
    norm = sorted({s.lower() if isinstance(s, str) else s for s in stack})
    assert "python" in norm and "react" in norm and "postgres" in norm
    assert intel.tech_stack.confidence == "high"


@pytest.mark.asyncio
async def test_fusion_skips_failed_providers():
    fusion = IntelFusion()
    results = [
        ProviderResult(provider="a", layer=1, success=False,
                       raw={"headcount": 999}, error="boom"),
        ProviderResult(provider="b", layer=1, success=True,
                       raw={"headcount": 50}),
    ]
    intel = await fusion.fuse("Acme", results)
    assert intel.headcount.value == 50
    assert intel.headcount.confidence == "medium"


@pytest.mark.asyncio
async def test_fusion_computes_completeness_and_high_count():
    fusion = IntelFusion()
    results = [
        ProviderResult(provider="a", layer=1, success=True,
                       raw={"headcount": 50, "tech_stack": ["Python"]}),
        ProviderResult(provider="b", layer=1, success=True,
                       raw={"headcount": 50}),
    ]
    intel = await fusion.fuse("Acme", results)
    assert intel.field_count >= 2
    assert intel.high_confidence_count >= 1
    assert 0.0 < intel.profile_completeness <= 1.0


@pytest.mark.asyncio
async def test_fusion_description_polish_uses_llm_then_falls_back():
    class _Boom:
        async def complete_json(self, **_kw: Any):
            raise RuntimeError("no llm")

    fusion = IntelFusion(ai_client=_Boom())
    results = [
        ProviderResult(provider="w", layer=2, success=True,
                       raw={"raw_about_text":
                            "Acme builds AI tools. We hire engineers."}),
    ]
    intel = await fusion.fuse("Acme", results)
    assert intel.description.value
    assert "Acme" in intel.description.value


# ─── application mapper ───────────────────────────────────────────

def _intel_with(**fields: Any) -> CompanyIntelV2:
    intel = CompanyIntelV2(company="Acme")
    for k, v in fields.items():
        from ai_engine.agents.sub_agents.recon_swarm.schemas import IntelField
        setattr(intel, k, IntelField(value=v, confidence="medium",
                                     sources=["test"]))
    return intel


def test_mapper_emits_kit_with_stack_overlap():
    intel = _intel_with(
        tech_stack=["Python", "FastAPI", "Postgres"],
        company_stage="series_b",
        headcount=200,
        last_round="Series B",
        leadership=[{"name": "Jane Doe", "title": "CEO"}],
        recent_news=[{"title": "Acme raises Series B"}],
        glassdoor_themes=["intense workload", "smart team"],
        glassdoor_rating=3.2,
        values=["ownership", "craft"],
    )
    kit = ApplicationMapper().map(
        intel,
        role_target="Senior Backend Engineer",
        candidate_skills=["Python", "FastAPI"],
        candidate_values=["learning"],
    )
    assert "python" in [s.lower() for s in kit.tech_stack_matches]
    assert any("Acme" in q or "?" in q for q in kit.interview_questions)
    assert any("Acme" in h for h in kit.cover_letter_hooks)
    # Glassdoor signals → red flags
    assert any("intense workload" in r.lower() or "3.2" in r
               for r in kit.red_flags)
    # Candidate value not matched → red flag
    assert any("learning" in r.lower() for r in kit.red_flags)


def test_mapper_minimal_intel_still_emits_safe_defaults():
    intel = CompanyIntelV2(company="Acme")
    kit = ApplicationMapper().map(intel)
    assert kit.resume_bullet_hooks
    assert kit.cover_letter_hooks
    assert kit.interview_questions
    assert kit.differentiation_angles


# ─── cache ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_memory_cache_set_get_and_stats():
    c = _MemoryCache()
    await c.set("k", {"x": 1}, ttl_s=60)
    v = await c.get("k")
    assert v == {"x": 1}
    miss = await c.get("nope")
    assert miss is None
    s = await c.stats()
    assert s["hits"] == 1 and s["misses"] == 1


# ─── coordinator end-to-end ───────────────────────────────────────

@pytest.mark.asyncio
async def test_coordinator_runs_all_layers_with_default_stubs():
    coord = ReconSwarmCoordinator(cache=_MemoryCache())
    req = ReconSwarmRequest(
        company="Acme",
        role_target="Senior Eng",
        candidate_skills=["Python"],
        budget_seconds=30,
    )
    report = await coord.run(req)
    assert report.layers_completed == [1, 2, 3, 4, 5]
    assert report.intel.field_count > 0
    assert report.application_kit.cover_letter_hooks
    assert report.cache_hit is False
    # Provider results from all stubs
    names = {r.provider for r in report.provider_results}
    assert "crunchbase_stub" in names
    assert "website_crawl_stub" in names


@pytest.mark.asyncio
async def test_coordinator_caches_then_short_circuits():
    cache = _MemoryCache()
    coord = ReconSwarmCoordinator(cache=cache)
    req = ReconSwarmRequest(company="Acme", budget_seconds=30)
    first = await coord.run(req)
    assert first.cache_hit is False
    second = await coord.run(req)
    assert second.cache_hit is True
    # No new provider results computed on cache hit (same shape from cache)
    assert second.intel.company == "Acme"


@pytest.mark.asyncio
async def test_coordinator_blank_company_raises():
    with pytest.raises(ValueError):
        await ReconSwarmCoordinator().run(
            ReconSwarmRequest(company="   ", budget_seconds=10),
        )


@pytest.mark.asyncio
async def test_coordinator_provider_failure_degrades_gracefully():
    class _Broken:
        name = "broken"
        layer = 1

        async def fetch(self, **_):
            raise RuntimeError("nope")

    coord = ReconSwarmCoordinator(
        layer1=[_Broken(), StubLinkedInProvider()],
        layer2=[],
        cache=_MemoryCache(),
    )
    report = await coord.run(
        ReconSwarmRequest(company="Acme", budget_seconds=10),
    )
    bad = next(r for r in report.provider_results if r.provider == "broken")
    assert bad.success is False
    assert "nope" in (bad.error or "")
    # Other provider still produced data
    assert report.intel.headcount.value is not None


# ─── tool registry ────────────────────────────────────────────────

def test_build_recon_swarm_tools_registers_one_tool():
    reg = build_recon_swarm_tools()
    tools = reg.list_tools()
    assert len(tools) == 1
    assert tools[0].name == "run_recon_swarm"
    schema = tools[0].parameters
    assert "input" in schema["properties"]
    assert schema["required"] == ["input"]


# ─── factories ────────────────────────────────────────────────────

def test_default_factories_return_expected_counts():
    assert len(default_layer1_providers()) == 5
    assert len(default_layer2_providers()) == 6


# ─── SEC EDGAR real provider (httpx injected) ───────────────────────

class _FakeResp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    def __init__(self, route_map: dict) -> None:
        self._routes = route_map
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> _FakeResp:
        self.calls.append(url)
        for prefix, resp in self._routes.items():
            if url.startswith(prefix):
                return resp
        return _FakeResp(404, {})

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_sec_edgar_real_provider_extracts_payload():
    tickers_payload = {
        "0": {"cik_str": 320193, "ticker": "AAPL",
              "title": "Apple Inc."},
        "1": {"cik_str": 789019, "ticker": "MSFT",
              "title": "Microsoft Corp"},
    }
    submissions_payload = {
        "name": "Apple Inc.",
        "tickers": ["AAPL"],
        "sicDescription": "Electronic Computers",
        "addresses": {"business": {"city": "Cupertino",
                                    "stateOrCountry": "CA"}},
        "formerNames": [{"name": "Apple Computer Inc."}],
    }
    client = _FakeClient({
        "https://www.sec.gov/files/company_tickers.json":
            _FakeResp(200, tickers_payload),
        "https://data.sec.gov/submissions/CIK0000320193.json":
            _FakeResp(200, submissions_payload),
    })
    p = SECEdgarProvider(http_client=client)
    r = await p.fetch(company="Apple")
    assert r.success is True
    assert r.raw["is_public"] is True
    assert r.raw["ticker"] == "AAPL"
    assert r.raw["legal_name"] == "Apple Inc."
    assert r.raw["industry"] == "Electronic Computers"
    assert r.raw["headquarters"] == "Cupertino, CA"
    assert "Apple Computer Inc." in r.raw["former_names"]


@pytest.mark.asyncio
async def test_sec_edgar_real_provider_unknown_company_returns_not_public():
    client = _FakeClient({
        "https://www.sec.gov/files/company_tickers.json":
            _FakeResp(200, {}),
    })
    p = SECEdgarProvider(http_client=client)
    r = await p.fetch(company="Some Private LLC")
    assert r.success is True
    assert r.raw == {"is_public": False}


@pytest.mark.asyncio
async def test_sec_edgar_real_provider_network_error_degrades():
    class _Boom:
        async def get(self, *_a: Any, **_kw: Any):
            raise RuntimeError("network down")

        async def aclose(self) -> None:
            pass

    p = SECEdgarProvider(http_client=_Boom())
    r = await p.fetch(company="Apple")
    assert r.success is False
    assert "network down" in (r.error or "")


def test_default_layer2_factory_swaps_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_SEC_PROVIDER", "real")
    providers = default_layer2_providers()
    sec = next(p for p in providers if p.name in {"sec", "sec_stub"})
    assert sec.name == "sec"
    monkeypatch.setenv("RECON_SEC_PROVIDER", "stub")
    providers2 = default_layer2_providers()
    sec2 = next(p for p in providers2 if p.name in {"sec", "sec_stub"})
    assert sec2.name == "sec_stub"
