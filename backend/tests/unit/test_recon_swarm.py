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
    GitHubProvider,
    GoogleNewsProvider,
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
    assert len(default_layer1_providers()) == 9
    assert len(default_layer2_providers()) == 6


# ─── SEC EDGAR real provider (httpx injected) ───────────────────────

class _FakeResp:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return self._payload if isinstance(self._payload, str) else ""


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


# ─── GitHub real provider tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_github_real_provider_extracts_payload():
    org_payload = {
        "login": "openai",
        "description": "AI research and deployment company.",
        "blog": "https://openai.com",
        "public_repos": 173,
    }
    repos = [
        {"name": "gym", "language": "Python"},
        {"name": "whisper", "language": "Python"},
        {"name": "openai-node", "language": "TypeScript"},
        {"name": "no-lang", "language": None},
    ]
    client = _FakeClient({
        "https://api.github.com/orgs/openai/repos":
            _FakeResp(200, repos),
        "https://api.github.com/orgs/openai":
            _FakeResp(200, org_payload),
    })
    p = GitHubProvider(http_client=client)
    r = await p.fetch(company="OpenAI")
    assert r.success is True
    assert r.raw["github_orgs"] == ["openai"]
    assert r.raw["repo_count"] == 173
    assert r.raw["languages"][0] == "Python"
    assert "TypeScript" in r.raw["languages"]
    assert r.raw["website"] == "https://openai.com"
    assert "AI research" in r.raw["description"]


@pytest.mark.asyncio
async def test_github_real_provider_org_not_found_degrades():
    client = _FakeClient({
        "https://api.github.com/orgs/totally-not-a-real-org":
            _FakeResp(404, {"message": "Not Found"}),
    })
    p = GitHubProvider(http_client=client)
    r = await p.fetch(company="totally not a real org")
    assert r.success is False
    assert "404" in (r.error or "")


@pytest.mark.asyncio
async def test_github_real_provider_network_error_degrades():
    class _Boom:
        async def get(self, *_a: Any, **_kw: Any):
            raise RuntimeError("github offline")

        async def aclose(self) -> None:
            pass

    p = GitHubProvider(http_client=_Boom())
    r = await p.fetch(company="OpenAI")
    assert r.success is False
    assert "github offline" in (r.error or "")


def test_github_provider_org_slug_derivation():
    cases = {
        "OpenAI": "openai",
        "Acme, Inc.": "acme-inc",
        "  Stripe  ": "stripe",
        "Hugging Face": "hugging-face",
        "": None,
        "   ": None,
    }
    for company, expected in cases.items():
        assert GitHubProvider._derive_org(company) == expected


def test_default_layer1_factory_swaps_github_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_GITHUB_PROVIDER", "real")
    providers = default_layer1_providers()
    gh = next(p for p in providers if p.name in {"github", "github_stub"})
    assert gh.name == "github"
    monkeypatch.setenv("RECON_GITHUB_PROVIDER", "stub")
    providers2 = default_layer1_providers()
    gh2 = next(p for p in providers2 if p.name in {"github", "github_stub"})
    assert gh2.name == "github_stub"


# ─── Google News real provider tests ──────────────────────────────────


_GNEWS_RSS_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<title>Google News</title>
<item>
  <title>Stripe launches new AI tool - TechCrunch</title>
  <link>https://news.google.com/...</link>
  <pubDate>Tue, 14 Apr 2026 10:30:00 GMT</pubDate>
  <source url="https://techcrunch.com">TechCrunch</source>
</item>
<item>
  <title>Stripe expands engineering team in Dublin - The Information</title>
  <link>https://news.google.com/...</link>
  <pubDate>Mon, 13 Apr 2026 09:00:00 GMT</pubDate>
</item>
<item>
  <title>Stripe and partners announce open standard</title>
  <pubDate>Fri, 10 Apr 2026 14:00:00 GMT</pubDate>
</item>
</channel></rss>"""


class _FakeTextResp:
    def __init__(self, status_code: int, text: str) -> None:
        self.status_code = status_code
        self.text = text


class _FakeTextClient:
    def __init__(self, status: int, text: str) -> None:
        self._resp = _FakeTextResp(status, text)
        self.calls: list[str] = []

    async def get(self, url: str, **_kw: Any) -> _FakeTextResp:
        self.calls.append(url)
        return self._resp

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_google_news_real_provider_parses_rss():
    client = _FakeTextClient(200, _GNEWS_RSS_SAMPLE)
    p = GoogleNewsProvider(http_client=client, max_items=5)
    r = await p.fetch(company="Stripe")
    assert r.success is True
    items = r.raw["recent_news"]
    assert len(items) == 3
    # Title-suffix source extraction
    assert items[0]["title"] == "Stripe launches new AI tool"
    assert items[0]["source"] == "TechCrunch"
    assert items[0]["date"] == "2026-04-14"
    assert items[1]["source"] == "The Information"
    # No source/title-suffix → default Google News
    assert items[2]["source"] == "Google News"
    # URL was query-encoded
    assert "Stripe" in client.calls[0] or "stripe" in client.calls[0].lower()


@pytest.mark.asyncio
async def test_google_news_real_provider_max_items_caps():
    client = _FakeTextClient(200, _GNEWS_RSS_SAMPLE)
    p = GoogleNewsProvider(http_client=client, max_items=2)
    r = await p.fetch(company="Stripe")
    assert r.success is True
    assert len(r.raw["recent_news"]) == 2


@pytest.mark.asyncio
async def test_google_news_real_provider_empty_company_fails_fast():
    client = _FakeTextClient(200, _GNEWS_RSS_SAMPLE)
    p = GoogleNewsProvider(http_client=client)
    r = await p.fetch(company="   ")
    assert r.success is False
    assert "empty" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_google_news_real_provider_bad_xml_returns_empty():
    client = _FakeTextClient(200, "<<<not-xml")
    p = GoogleNewsProvider(http_client=client)
    r = await p.fetch(company="Stripe")
    assert r.success is True
    assert r.raw["recent_news"] == []


@pytest.mark.asyncio
async def test_google_news_real_provider_non_200_degrades():
    client = _FakeTextClient(503, "service unavailable")
    p = GoogleNewsProvider(http_client=client)
    r = await p.fetch(company="Stripe")
    assert r.success is False
    assert "503" in (r.error or "")


@pytest.mark.asyncio
async def test_google_news_real_provider_network_error_degrades():
    class _Boom:
        async def get(self, *_a: Any, **_kw: Any):
            raise RuntimeError("rss offline")

        async def aclose(self) -> None:
            pass

    p = GoogleNewsProvider(http_client=_Boom())
    r = await p.fetch(company="Stripe")
    assert r.success is False
    assert "rss offline" in (r.error or "")


def test_default_layer1_factory_swaps_news_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_GOOGLE_NEWS_PROVIDER", "real")
    monkeypatch.setenv("RECON_GITHUB_PROVIDER", "stub")
    providers = default_layer1_providers()
    news = next(p for p in providers
                if p.name in {"google_news", "google_news_stub"})
    assert news.name == "google_news"
    monkeypatch.setenv("RECON_GOOGLE_NEWS_PROVIDER", "stub")
    providers2 = default_layer1_providers()
    news2 = next(p for p in providers2
                 if p.name in {"google_news", "google_news_stub"})
    assert news2.name == "google_news_stub"


# ─── Hacker News real provider (httpx injected) ───────────────────

from ai_engine.agents.sub_agents.recon_swarm import (  # noqa: E402
    HackerNewsProvider,
    StubHackerNewsProvider,
)


@pytest.mark.asyncio
async def test_stub_hackernews_returns_recent_news_items():
    p = StubHackerNewsProvider()
    r = await p.fetch(company="Stripe")
    assert r.success is True
    assert r.layer == 1
    items = r.raw["recent_news"]
    assert isinstance(items, list) and len(items) >= 1
    assert all("title" in it and "source" in it for it in items)
    assert any("Stripe" in it["title"] for it in items)


@pytest.mark.asyncio
async def test_hackernews_real_provider_extracts_hits():
    payload = {
        "hits": [
            {"title": "Show HN: OpenAI launches Sora",
             "url": "https://example.com/sora",
             "created_at": "2026-04-01T12:34:56Z",
             "points": 412, "num_comments": 188},
            {"story_title": "OpenAI ships GPT-6",
             "story_url": "https://example.com/gpt6",
             "created_at": "2026-03-20T09:00:00Z",
             "points": 999, "num_comments": 543},
            {"title": "", "url": "https://example.com/empty"},  # skipped
        ],
    }
    client = _FakeClient({
        "https://hn.algolia.com/api/v1/search": _FakeResp(200, payload),
    })
    p = HackerNewsProvider(http_client=client, max_items=5)
    r = await p.fetch(company="OpenAI")
    assert r.success is True
    items = r.raw["recent_news"]
    assert len(items) == 2
    assert items[0]["title"].startswith("Show HN")
    assert items[0]["source"] == "Hacker News"
    assert items[0]["date"] == "2026-04-01"
    assert items[0]["points"] == 412
    assert items[1]["title"] == "OpenAI ships GPT-6"
    assert items[1]["url"] == "https://example.com/gpt6"


@pytest.mark.asyncio
async def test_hackernews_real_provider_respects_max_items():
    hits = [
        {"title": f"story {i}", "url": f"https://x/{i}",
         "created_at": "2026-01-01T00:00:00Z",
         "points": 10, "num_comments": 1}
        for i in range(20)
    ]
    client = _FakeClient({
        "https://hn.algolia.com/api/v1/search":
            _FakeResp(200, {"hits": hits}),
    })
    p = HackerNewsProvider(http_client=client, max_items=3)
    r = await p.fetch(company="Acme")
    assert r.success is True
    assert len(r.raw["recent_news"]) == 3


@pytest.mark.asyncio
async def test_hackernews_real_provider_handles_non_200():
    client = _FakeClient({
        "https://hn.algolia.com/api/v1/search":
            _FakeResp(503, {"error": "service unavailable"}),
    })
    p = HackerNewsProvider(http_client=client)
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "503" in (r.error or "")


@pytest.mark.asyncio
async def test_hackernews_real_provider_empty_company_fails_fast():
    p = HackerNewsProvider()
    r = await p.fetch(company="")
    assert r.success is False
    assert r.error == "empty company"


@pytest.mark.asyncio
async def test_hackernews_real_provider_swallows_network_exceptions():
    class _BoomClient:
        async def get(self, url, **_kw):
            raise RuntimeError("connection reset")

        async def aclose(self):
            pass

    p = HackerNewsProvider(http_client=_BoomClient())
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "connection reset" in (r.error or "")


def test_default_layer1_factory_swaps_hackernews_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_HACKERNEWS_PROVIDER", "real")
    providers = default_layer1_providers()
    hn = next(p for p in providers
              if p.name in {"hacker_news", "hacker_news_stub"})
    assert hn.name == "hacker_news"
    monkeypatch.setenv("RECON_HACKERNEWS_PROVIDER", "stub")
    providers2 = default_layer1_providers()
    hn2 = next(p for p in providers2
               if p.name in {"hacker_news", "hacker_news_stub"})
    assert hn2.name == "hacker_news_stub"


# ─── Wikipedia real provider (Layer 2, opt-in) ────────────────────

from ai_engine.agents.sub_agents.recon_swarm import WikipediaProvider  # noqa: E402


_WIKI_APPLE_SUMMARY = {
    "type": "standard",
    "title": "Apple Inc.",
    "description": "American multinational technology company",
    "extract": (
        "Apple Inc. is an American multinational technology company "
        "headquartered in Cupertino, California. Apple was founded in "
        "1976 by Steve Jobs, Steve Wozniak, and Ronald Wayne. The "
        "company designs consumer electronics."
    ),
    "content_urls": {
        "desktop": {"page": "https://en.wikipedia.org/wiki/Apple_Inc."},
    },
}


@pytest.mark.asyncio
async def test_wikipedia_real_provider_extracts_payload():
    client = _FakeClient({
        "https://en.wikipedia.org/api/rest_v1/page/summary/Apple_Inc":
            _FakeResp(200, _WIKI_APPLE_SUMMARY),
        # Wider key for any Apple variant.
        "https://en.wikipedia.org/api/rest_v1/page/summary/Apple":
            _FakeResp(200, _WIKI_APPLE_SUMMARY),
    })
    p = WikipediaProvider(http_client=client)
    r = await p.fetch(company="Apple")
    assert r.success is True
    assert r.layer == 2
    assert r.raw["legal_name"] == "Apple Inc."
    assert r.raw["industry"].startswith("American multinational")
    assert r.raw["founded_year"] == 1976
    assert "Cupertino" in r.raw["description"]
    assert r.raw["wikipedia_url"].endswith("Apple_Inc.")


@pytest.mark.asyncio
async def test_wikipedia_real_provider_falls_back_to_opensearch():
    # Direct lookup 404s, opensearch returns first hit, then summary 200.
    summary_payload = {
        "type": "standard",
        "title": "OpenAI",
        "description": "AI research and deployment company",
        "extract": "OpenAI is an American AI research lab founded in 2015.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/OpenAI"}},
    }

    class _Routed:
        async def get(self, url, **_kw):
            if url.startswith("https://en.wikipedia.org/api/rest_v1/page/summary/OpenAI_Co"):
                return _FakeResp(404, {"detail": "not found"})
            if url.startswith("https://en.wikipedia.org/w/api.php"):
                # Opensearch shape: [query, [titles], [descs], [urls]]
                return _FakeResp(200, ["OpenAI Co", ["OpenAI"], [""], [""]])
            if url.startswith("https://en.wikipedia.org/api/rest_v1/page/summary/OpenAI"):
                return _FakeResp(200, summary_payload)
            return _FakeResp(404, {})

        async def aclose(self):
            pass

    p = WikipediaProvider(http_client=_Routed())
    r = await p.fetch(company="OpenAI Co")
    assert r.success is True
    assert r.raw["legal_name"] == "OpenAI"
    assert r.raw["founded_year"] == 2015


@pytest.mark.asyncio
async def test_wikipedia_real_provider_skips_disambiguation_then_searches():
    disambig = {"type": "disambiguation", "title": "Acme",
                "extract": "Acme may refer to:"}

    class _Routed:
        async def get(self, url, **_kw):
            if url.startswith("https://en.wikipedia.org/api/rest_v1/page/summary/Acme"):
                # Direct title hits, but disambiguation \u2192 should fall through.
                return _FakeResp(200, disambig)
            if url.startswith("https://en.wikipedia.org/w/api.php"):
                return _FakeResp(200, ["Acme", [], [], []])
            return _FakeResp(404, {})

        async def aclose(self):
            pass

    p = WikipediaProvider(http_client=_Routed())
    r = await p.fetch(company="Acme")
    # Disambiguation \u2192 falls through to opensearch \u2192 empty titles
    # \u2192 success with empty raw.
    assert r.success is True
    assert r.raw == {} or r.raw.get("legal_name") is None


@pytest.mark.asyncio
async def test_wikipedia_real_provider_empty_company_fails_fast():
    p = WikipediaProvider()
    r = await p.fetch(company="")
    assert r.success is False
    assert r.error == "empty company"


@pytest.mark.asyncio
async def test_wikipedia_real_provider_swallows_exceptions():
    class _Boom:
        async def get(self, url, **_kw):
            raise RuntimeError("dns fail")

        async def aclose(self):
            pass

    p = WikipediaProvider(http_client=_Boom())
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "dns fail" in (r.error or "")


def test_wikipedia_extract_founded_year_parser():
    assert WikipediaProvider._extract_founded_year(
        "founded in 1998 by Larry Page") == 1998
    assert WikipediaProvider._extract_founded_year(
        "established in 1903 in Detroit") == 1903
    assert WikipediaProvider._extract_founded_year(
        "incorporated on June 4, 2007") == 2007
    assert WikipediaProvider._extract_founded_year("no year here") is None
    # Invalid year range \u2192 None.
    assert WikipediaProvider._extract_founded_year("founded 1500 BC") is None


def test_default_layer2_factory_appends_wikipedia_when_env_set(monkeypatch):
    monkeypatch.delenv("RECON_WIKIPEDIA_PROVIDER", raising=False)
    base = default_layer2_providers()
    assert all(p.name != "wikipedia" for p in base)
    assert len(base) == 6
    monkeypatch.setenv("RECON_WIKIPEDIA_PROVIDER", "real")
    grown = default_layer2_providers()
    assert any(p.name == "wikipedia" for p in grown)
    assert len(grown) == 7


# ─── Reddit real provider (httpx injected) ────────────────────────

from ai_engine.agents.sub_agents.recon_swarm import (  # noqa: E402
    RedditProvider,
    StubRedditProvider,
)


@pytest.mark.asyncio
async def test_stub_reddit_returns_recent_news_items():
    p = StubRedditProvider()
    r = await p.fetch(company="Stripe")
    assert r.success is True
    assert r.layer == 1
    items = r.raw["recent_news"]
    assert isinstance(items, list) and len(items) >= 1
    assert all("title" in it and "source" in it for it in items)
    assert any("Stripe" in it["title"] for it in items)


@pytest.mark.asyncio
async def test_reddit_real_provider_extracts_hits():
    payload = {
        "data": {
            "children": [
                {"data": {
                    "title": "Has anyone interviewed at Stripe recently?",
                    "permalink": "/r/cscareerquestions/comments/abc/",
                    "subreddit": "cscareerquestions",
                    "created_utc": 1733097600,  # 2024-12-02 UTC
                    "score": 142, "num_comments": 88,
                }},
                {"data": {
                    "title": "Stripe internship review",
                    "url": "https://reddit.com/r/csmajors/xyz",
                    "subreddit": "csmajors",
                    "created_utc": 1730000000,
                    "score": 50, "num_comments": 12,
                }},
                {"data": {"title": ""}},  # skipped
            ],
        },
    }
    client = _FakeClient({
        "https://www.reddit.com/search.json": _FakeResp(200, payload),
    })
    p = RedditProvider(http_client=client, max_items=5)
    r = await p.fetch(company="Stripe")
    assert r.success is True
    items = r.raw["recent_news"]
    assert len(items) == 2
    assert items[0]["title"].startswith("Has anyone interviewed")
    assert items[0]["source"] == "Reddit r/cscareerquestions"
    assert items[0]["url"].startswith(
        "https://www.reddit.com/r/cscareerquestions",
    )
    assert items[0]["date"]  # parsed
    assert items[0]["score"] == 142
    assert items[1]["source"] == "Reddit r/csmajors"


@pytest.mark.asyncio
async def test_reddit_real_provider_respects_max_items():
    children = [
        {"data": {
            "title": f"post {i}",
            "permalink": f"/r/x/{i}/",
            "subreddit": "x",
            "created_utc": 1730000000 + i,
            "score": 1, "num_comments": 1,
        }}
        for i in range(20)
    ]
    client = _FakeClient({
        "https://www.reddit.com/search.json":
            _FakeResp(200, {"data": {"children": children}}),
    })
    p = RedditProvider(http_client=client, max_items=4)
    r = await p.fetch(company="Acme")
    assert r.success is True
    assert len(r.raw["recent_news"]) == 4


@pytest.mark.asyncio
async def test_reddit_real_provider_handles_non_200():
    client = _FakeClient({
        "https://www.reddit.com/search.json":
            _FakeResp(429, {"error": "rate limited"}),
    })
    p = RedditProvider(http_client=client)
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "429" in (r.error or "")


@pytest.mark.asyncio
async def test_reddit_real_provider_empty_company_fails_fast():
    p = RedditProvider()
    r = await p.fetch(company="")
    assert r.success is False
    assert r.error == "empty company"


@pytest.mark.asyncio
async def test_reddit_real_provider_swallows_network_exceptions():
    class _BoomClient:
        async def get(self, url, **_kw):
            raise RuntimeError("dns failure")

        async def aclose(self):
            pass

    p = RedditProvider(http_client=_BoomClient())
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "dns failure" in (r.error or "")


def test_default_layer1_factory_swaps_reddit_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_REDDIT_PROVIDER", "real")
    providers = default_layer1_providers()
    rd = next(p for p in providers
              if p.name in {"reddit", "reddit_stub"})
    assert rd.name == "reddit"
    monkeypatch.setenv("RECON_REDDIT_PROVIDER", "stub")
    providers2 = default_layer1_providers()
    rd2 = next(p for p in providers2
               if p.name in {"reddit", "reddit_stub"})
    assert rd2.name == "reddit_stub"


# ─── Stack Exchange real provider (httpx injected) ────────────────

from ai_engine.agents.sub_agents.recon_swarm import (  # noqa: E402
    StackExchangeProvider,
    StubStackExchangeProvider,
)


@pytest.mark.asyncio
async def test_stub_stackexchange_returns_recent_news_items():
    p = StubStackExchangeProvider()
    r = await p.fetch(company="Stripe")
    assert r.success is True
    assert r.layer == 1
    items = r.raw["recent_news"]
    assert isinstance(items, list) and len(items) >= 1
    assert all("title" in it and it["source"] == "Stack Overflow"
               for it in items)


@pytest.mark.asyncio
async def test_stackexchange_real_provider_extracts_questions():
    payload = {
        "items": [
            {
                "title": "How to handle Stripe webhook idempotency?",
                "link": "https://stackoverflow.com/q/12345",
                "creation_date": 1733097600,
                "score": 42, "answer_count": 3,
                "is_answered": True,
                "tags": ["stripe-payments", "webhooks", "node.js"],
            },
            {
                # &amp; should be unescaped
                "title": "Stripe API &amp; idempotency keys",
                "link": "https://stackoverflow.com/q/67890",
                "creation_date": 1730000000,
                "score": 12, "answer_count": 1,
                "is_answered": False,
                "tags": ["stripe-payments"],
            },
            {"title": ""},  # skipped
        ],
    }
    client = _FakeClient({
        "https://api.stackexchange.com/2.3/search/advanced":
            _FakeResp(200, payload),
    })
    p = StackExchangeProvider(http_client=client, max_items=5)
    r = await p.fetch(company="Stripe")
    assert r.success is True
    items = r.raw["recent_news"]
    assert len(items) == 2
    assert items[0]["title"] == "How to handle Stripe webhook idempotency?"
    assert items[0]["source"] == "Stack Overflow"
    assert items[0]["score"] == 42
    assert items[0]["is_answered"] is True
    assert "stripe-payments" in items[0]["tags"]
    assert items[0]["date"]  # parsed
    # html unescape
    assert items[1]["title"] == "Stripe API & idempotency keys"


@pytest.mark.asyncio
async def test_stackexchange_real_provider_respects_max_items():
    items = [
        {"title": f"q{i}", "link": f"https://so.com/{i}",
         "creation_date": 1730000000 + i,
         "score": 1, "answer_count": 0, "tags": []}
        for i in range(20)
    ]
    client = _FakeClient({
        "https://api.stackexchange.com/2.3/search/advanced":
            _FakeResp(200, {"items": items}),
    })
    p = StackExchangeProvider(http_client=client, max_items=4)
    r = await p.fetch(company="Acme")
    assert r.success is True
    assert len(r.raw["recent_news"]) == 4


@pytest.mark.asyncio
async def test_stackexchange_real_provider_handles_non_200():
    client = _FakeClient({
        "https://api.stackexchange.com/2.3/search/advanced":
            _FakeResp(429, {"error": "throttle"}),
    })
    p = StackExchangeProvider(http_client=client)
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "429" in (r.error or "")


@pytest.mark.asyncio
async def test_stackexchange_real_provider_empty_company_fails_fast():
    p = StackExchangeProvider()
    r = await p.fetch(company="")
    assert r.success is False
    assert r.error == "empty company"


@pytest.mark.asyncio
async def test_stackexchange_real_provider_swallows_network_exceptions():
    class _BoomClient:
        async def get(self, url, **_kw):
            raise RuntimeError("read timeout")

        async def aclose(self):
            pass

    p = StackExchangeProvider(http_client=_BoomClient())
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "read timeout" in (r.error or "")


def test_default_layer1_factory_swaps_stackexchange_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_STACKEXCHANGE_PROVIDER", "real")
    providers = default_layer1_providers()
    se = next(p for p in providers
              if p.name in {"stackexchange", "stackexchange_stub"})
    assert se.name == "stackexchange"
    monkeypatch.setenv("RECON_STACKEXCHANGE_PROVIDER", "stub")
    providers2 = default_layer1_providers()
    se2 = next(p for p in providers2
               if p.name in {"stackexchange", "stackexchange_stub"})
    assert se2.name == "stackexchange_stub"


# ─── arXiv real provider (httpx injected) ───────────────────────────

from ai_engine.agents.sub_agents.recon_swarm import (  # noqa: E402
    ArxivProvider,
    StubArxivProvider,
)


_ARXIV_SAMPLE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.12345v1</id>
    <title>Scaling laws for Acme &amp; Friends</title>
    <published>2026-04-01T00:00:00Z</published>
    <author><name>Alice Researcher</name></author>
    <author><name>Bob Scientist</name></author>
    <arxiv:primary_category xmlns:arxiv="http://arxiv.org/schemas/atom"
                            term="cs.LG" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.99999v2</id>
    <title>Second paper</title>
    <published>2026-03-15T00:00:00Z</published>
    <author><name>Charlie</name></author>
  </entry>
</feed>
"""


@pytest.mark.asyncio
async def test_stub_arxiv_returns_research_papers():
    p = StubArxivProvider()
    r = await p.fetch(company="OpenAI")
    assert r.success is True
    items = r.raw.get("research_papers", [])
    assert len(items) >= 1
    assert items[0]["source"] == "arXiv"


@pytest.mark.asyncio
async def test_arxiv_real_provider_extracts_papers():
    client = _FakeClient({
        "https://export.arxiv.org/api/query":
            _FakeResp(200, _ARXIV_SAMPLE_XML),
    })
    p = ArxivProvider(http_client=client, max_items=5)
    r = await p.fetch(company="Acme")
    assert r.success is True
    papers = r.raw.get("research_papers", [])
    assert len(papers) == 2
    p0 = papers[0]
    assert p0["title"] == "Scaling laws for Acme & Friends"
    assert p0["url"] == "http://arxiv.org/abs/2401.12345v1"
    assert p0["date"] == "2026-04-01"
    assert p0["source"] == "arXiv"
    assert p0["authors"] == ["Alice Researcher", "Bob Scientist"]
    assert p0["category"] == "cs.LG"
    assert papers[1]["category"] == ""


@pytest.mark.asyncio
async def test_arxiv_real_provider_respects_max_items():
    client = _FakeClient({
        "https://export.arxiv.org/api/query":
            _FakeResp(200, _ARXIV_SAMPLE_XML),
    })
    p = ArxivProvider(http_client=client, max_items=1)
    r = await p.fetch(company="Acme")
    assert r.success is True
    assert len(r.raw["research_papers"]) == 1


@pytest.mark.asyncio
async def test_arxiv_real_provider_handles_non_200():
    client = _FakeClient({
        "https://export.arxiv.org/api/query":
            _FakeResp(503, "service unavailable"),
    })
    p = ArxivProvider(http_client=client)
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "503" in (r.error or "")


@pytest.mark.asyncio
async def test_arxiv_real_provider_empty_company_fails_fast():
    client = _FakeClient({})
    p = ArxivProvider(http_client=client)
    r = await p.fetch(company="   ")
    assert r.success is False
    assert "empty" in (r.error or "").lower()


@pytest.mark.asyncio
async def test_arxiv_real_provider_handles_malformed_xml():
    client = _FakeClient({
        "https://export.arxiv.org/api/query":
            _FakeResp(200, "<<<not xml>>>"),
    })
    p = ArxivProvider(http_client=client)
    r = await p.fetch(company="Acme")
    # Bad XML returns success=True with empty list (degrades silently)
    assert r.success is True
    assert r.raw["research_papers"] == []


@pytest.mark.asyncio
async def test_arxiv_real_provider_swallows_network_exceptions():
    class _BoomClient:
        async def get(self, url, **_kw):
            raise RuntimeError("dns failure")

        async def aclose(self):
            pass

    p = ArxivProvider(http_client=_BoomClient())
    r = await p.fetch(company="Acme")
    assert r.success is False
    assert "dns failure" in (r.error or "")


def test_default_layer1_factory_swaps_arxiv_to_real_when_env_set(monkeypatch):
    monkeypatch.setenv("RECON_ARXIV_PROVIDER", "real")
    providers = default_layer1_providers()
    ax = next(p for p in providers
              if p.name in {"arxiv", "arxiv_stub"})
    assert ax.name == "arxiv"
    monkeypatch.setenv("RECON_ARXIV_PROVIDER", "stub")
    providers2 = default_layer1_providers()
    ax2 = next(p for p in providers2
               if p.name in {"arxiv", "arxiv_stub"})
    assert ax2.name == "arxiv_stub"


@pytest.mark.asyncio
async def test_fusion_merges_research_papers_from_arxiv():
    fusion = IntelFusion()
    paper_a = {"title": "Paper A", "url": "http://arxiv.org/abs/1",
               "source": "arXiv", "date": "2026-04-01"}
    paper_b = {"title": "Paper B", "url": "http://arxiv.org/abs/2",
               "source": "arXiv", "date": "2026-03-15"}
    results = [
        ProviderResult(provider="arxiv", layer=1, success=True,
                       raw={"research_papers": [paper_a, paper_b]}),
    ]
    intel = await fusion.fuse("Acme", results)
    papers = intel.research_papers.value
    assert isinstance(papers, list)
    titles = {p.get("title") for p in papers if isinstance(p, dict)}
    assert {"Paper A", "Paper B"} <= titles


def test_mapper_uses_research_papers_when_available():
    intel = _intel_with(
        research_papers=[
            {"title": "Scaling Acme to 1B QPS",
             "url": "http://arxiv.org/abs/123",
             "source": "arXiv"},
            {"title": "Acme Optimizer v2",
             "url": "http://arxiv.org/abs/456"},
        ],
    )
    kit = ApplicationMapper().map(intel, role_target="ML Engineer")
    # interview question references the paper
    assert any("Scaling Acme to 1B QPS" in q for q in kit.interview_questions)
    # talking point references the paper
    assert any("Scaling Acme to 1B QPS" in t for t in kit.talking_points)
    # differentiation angle mentions research
    assert any("research" in d.lower() or "arxiv" in d.lower()
               for d in kit.differentiation_angles)


def test_mapper_skips_research_papers_when_empty():
    intel = _intel_with(tech_stack=["Python"])
    kit = ApplicationMapper().map(intel)
    # No research papers → no arXiv mentions
    assert not any("arxiv" in q.lower() for q in kit.interview_questions)


def test_mapper_uses_sec_risk_factors():
    intel = _intel_with(
        sec_risk_factors=["Concentration risk in top 3 customers",
                          "Regulatory exposure in EU"],
    )
    kit = ApplicationMapper().map(intel, role_target="Strategy Lead")
    assert any("Concentration risk in top 3 customers" in q
               for q in kit.interview_questions)
    assert any("10-K" in q for q in kit.interview_questions)


def test_mapper_uses_product_launches():
    intel = _intel_with(
        product_launches=[{"name": "Acme v3", "date": "2026-04-15"}],
    )
    kit = ApplicationMapper().map(intel, role_target="PM")
    assert any("Acme v3" in q for q in kit.interview_questions)


def test_mapper_uses_products_in_talking_points():
    intel = _intel_with(products=["Acme API", "Acme Pay"])
    kit = ApplicationMapper().map(intel)
    assert any("Acme API" in t for t in kit.talking_points)


def test_mapper_flags_work_style_mismatch():
    intel = _intel_with(work_style="onsite")
    kit = ApplicationMapper().map(
        intel,
        candidate_values=["remote"],
    )
    assert any("work-style" in r.lower() and "onsite" in r.lower()
               for r in kit.red_flags)


def test_mapper_no_work_style_red_flag_when_aligned():
    intel = _intel_with(work_style="remote-first")
    kit = ApplicationMapper().map(
        intel,
        candidate_values=["remote"],
    )
    assert not any("work-style" in r.lower() for r in kit.red_flags)


def test_mapper_uses_investors_in_cover_letter():
    intel = _intel_with(investors=["Sequoia", "a16z", "Founders Fund"])
    kit = ApplicationMapper().map(intel)
    assert any("Sequoia" in h and "a16z" in h for h in kit.cover_letter_hooks)


def test_mapper_uses_valuation_in_interview_question():
    intel = _intel_with(valuation_usd=2_500_000_000)
    kit = ApplicationMapper().map(intel, role_target="VP Eng")
    assert any("$2.5B" in q for q in kit.interview_questions)


def test_mapper_handles_small_valuation():
    intel = _intel_with(valuation_usd=85_000_000)
    kit = ApplicationMapper().map(intel)
    assert any("$85M" in q for q in kit.interview_questions)


# ─── Wikidata real provider (httpx injected) ───────────────────────

@pytest.mark.asyncio
async def test_wikidata_provider_extracts_company_facts():
    from ai_engine.agents.sub_agents.recon_swarm.providers import WikidataProvider
    search_payload = {
        "search": [
            {"id": "Q312", "label": "Apple Inc.", "description": "tech co"},
        ]
    }
    entity_payload = {
        "entities": {
            "Q312": {
                "claims": {
                    "P571": [{"mainsnak": {"snaktype": "value",
                                            "datavalue": {"value": {
                                                "time": "+1976-04-01T00:00:00Z"
                                            }}}}],
                    "P159": [{"mainsnak": {"snaktype": "value",
                                            "datavalue": {"value": {
                                                "id": "Q1413102"
                                            }}}}],
                    "P112": [
                        {"mainsnak": {"snaktype": "value",
                                       "datavalue": {"value": {"id": "Q19837"}}}},
                        {"mainsnak": {"snaktype": "value",
                                       "datavalue": {"value": {"id": "Q312087"}}}},
                    ],
                    "P249": [{"mainsnak": {"snaktype": "value",
                                            "datavalue": {"value": "AAPL"}}}],
                    "P856": [{"mainsnak": {"snaktype": "value",
                                            "datavalue": {"value": "https://www.apple.com/"}}}],
                    "P1128": [{"mainsnak": {"snaktype": "value",
                                             "datavalue": {"value": {
                                                 "amount": "+161000"
                                             }}}}],
                }
            }
        }
    }
    labels_payload = {
        "entities": {
            "Q1413102": {"labels": {"en": {"language": "en",
                                            "value": "Cupertino"}}},
            "Q19837":   {"labels": {"en": {"language": "en",
                                            "value": "Steve Jobs"}}},
            "Q312087":  {"labels": {"en": {"language": "en",
                                            "value": "Steve Wozniak"}}},
        }
    }
    client = _FakeClient({
        "https://www.wikidata.org/w/api.php?action=wbsearchentities":
            _FakeResp(200, search_payload),
        "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q312&props=claims":
            _FakeResp(200, entity_payload),
        "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q1413102|Q19837|Q312087":
            _FakeResp(200, labels_payload),
    })
    p = WikidataProvider(http_client=client)
    r = await p.fetch(company="Apple")
    assert r.success is True
    assert r.raw["wikidata_qid"] == "Q312"
    assert r.raw["founded_year"] == 1976
    assert r.raw["headquarters"] == "Cupertino"
    assert r.raw["ticker"] == "AAPL"
    assert r.raw["website"] == "https://www.apple.com/"
    assert r.raw["eng_headcount"] == 161000
    leadership = r.raw["leadership"]
    names = {entry["name"] for entry in leadership}
    assert "Steve Jobs" in names
    assert "Steve Wozniak" in names
    assert all(entry["title"] == "Founder" for entry in leadership)


@pytest.mark.asyncio
async def test_wikidata_provider_no_match_returns_failure():
    from ai_engine.agents.sub_agents.recon_swarm.providers import WikidataProvider
    client = _FakeClient({
        "https://www.wikidata.org/w/api.php?action=wbsearchentities":
            _FakeResp(200, {"search": []}),
    })
    p = WikidataProvider(http_client=client)
    r = await p.fetch(company="Nonexistent Co")
    assert r.success is False
    assert r.raw == {}


@pytest.mark.asyncio
async def test_wikidata_provider_handles_partial_claims():
    """Company with only founded_year + ticker, no HQ/founder."""
    from ai_engine.agents.sub_agents.recon_swarm.providers import WikidataProvider
    search_payload = {"search": [{"id": "Q999"}]}
    entity_payload = {
        "entities": {
            "Q999": {
                "claims": {
                    "P571": [{"mainsnak": {"snaktype": "value",
                                            "datavalue": {"value": {
                                                "time": "+2015-06-01T00:00:00Z"
                                            }}}}],
                    "P249": [{"mainsnak": {"snaktype": "value",
                                            "datavalue": {"value": "TEST"}}}],
                }
            }
        }
    }
    client = _FakeClient({
        "https://www.wikidata.org/w/api.php?action=wbsearchentities":
            _FakeResp(200, search_payload),
        "https://www.wikidata.org/w/api.php?action=wbgetentities&ids=Q999&props=claims":
            _FakeResp(200, entity_payload),
    })
    p = WikidataProvider(http_client=client)
    r = await p.fetch(company="Test Co")
    assert r.success is True
    assert r.raw["founded_year"] == 2015
    assert r.raw["ticker"] == "TEST"
    assert "headquarters" not in r.raw
    assert "leadership" not in r.raw


@pytest.mark.asyncio
async def test_wikidata_provider_empty_company_returns_failure():
    from ai_engine.agents.sub_agents.recon_swarm.providers import WikidataProvider
    p = WikidataProvider(http_client=_FakeClient({}))
    r = await p.fetch(company="   ")
    assert r.success is False


@pytest.mark.asyncio
async def test_wikidata_provider_handles_500():
    from ai_engine.agents.sub_agents.recon_swarm.providers import WikidataProvider
    client = _FakeClient({
        "https://www.wikidata.org/w/api.php?action=wbsearchentities":
            _FakeResp(500, {}),
    })
    p = WikidataProvider(http_client=client)
    r = await p.fetch(company="Apple")
    assert r.success is False


def test_wikidata_provider_in_layer2_factory_when_enabled(monkeypatch):
    from ai_engine.agents.sub_agents.recon_swarm.providers import (
        WikidataProvider, default_layer2_providers,
    )
    monkeypatch.setenv("RECON_WIKIDATA_PROVIDER", "real")
    provs = default_layer2_providers()
    assert any(isinstance(p, WikidataProvider) for p in provs)


def test_wikidata_provider_off_by_default():
    from ai_engine.agents.sub_agents.recon_swarm.providers import (
        WikidataProvider, default_layer2_providers,
    )
    # default env: should NOT include WikidataProvider
    provs = default_layer2_providers()
    assert not any(isinstance(p, WikidataProvider) for p in provs)


def test_mapper_uses_github_orgs_in_cover_letter():
    intel = _intel_with(github_orgs=["acmecorp", "acme-labs"])
    kit = ApplicationMapper().map(intel)
    assert any(
        "acmecorp" in h and "acme-labs" in h and "PR" in h
        for h in kit.cover_letter_hooks
    )


def test_mapper_uses_patents_count_in_interview_question():
    intel = _intel_with(patents_count=42)
    kit = ApplicationMapper().map(intel, role_target="Principal Engineer")
    assert any(
        "42 granted patents" in q and "R&D" in q for q in kit.interview_questions
    )


def test_mapper_skips_zero_patents_count():
    intel = _intel_with(patents_count=0)
    kit = ApplicationMapper().map(intel)
    assert not any("granted patents" in q for q in kit.interview_questions)


def test_mapper_adds_competitor_diff_angle():
    intel = _intel_with(competitors=["Stripe", "Adyen"])
    kit = ApplicationMapper().map(intel)
    assert any(
        "Stripe" in d and "specifically" in d for d in kit.differentiation_angles
    )


def test_mapper_adds_recent_news_talking_point():
    intel = _intel_with(recent_news=[
        {"title": "Acme launches B2B Studio", "url": "x", "date": "2026-04-01"}
    ])
    kit = ApplicationMapper().map(intel)
    assert any(
        "Acme launches B2B Studio" in t and "active tracking" in t
        for t in kit.talking_points
    )


# ─── Schema/fusion: wikipedia_url + wikidata deep links ─────────────

@pytest.mark.asyncio
async def test_fusion_persists_wikipedia_url_through_pipeline():
    """Wikipedia provider populates wikipedia_url; fusion must surface it."""
    from ai_engine.agents.sub_agents.recon_swarm.intel_fusion import IntelFusion
    from ai_engine.agents.sub_agents.recon_swarm.schemas import ProviderResult
    pr = ProviderResult(
        provider="wikipedia", layer=2, success=True, latency_ms=12,
        raw={"wikipedia_url": "https://en.wikipedia.org/wiki/Apple_Inc."},
    )
    intel = await IntelFusion().fuse(company="Apple", results=[pr])
    assert intel.wikipedia_url.value == "https://en.wikipedia.org/wiki/Apple_Inc."


@pytest.mark.asyncio
async def test_fusion_persists_wikidata_url_and_qid():
    from ai_engine.agents.sub_agents.recon_swarm.intel_fusion import IntelFusion
    from ai_engine.agents.sub_agents.recon_swarm.schemas import ProviderResult
    pr = ProviderResult(
        provider="wikidata", layer=2, success=True, latency_ms=18,
        raw={
            "wikidata_qid": "Q312",
            "wikidata_url": "https://www.wikidata.org/wiki/Q312",
            "founded_year": 1976,
        },
    )
    intel = await IntelFusion().fuse(company="Apple", results=[pr])
    assert intel.wikidata_qid.value == "Q312"
    assert intel.wikidata_url.value == "https://www.wikidata.org/wiki/Q312"
    assert intel.founded_year.value == 1976


def test_bridge_wires_wikidata_url_into_company_overview():
    from ai_engine.chains.recon_swarm_bridge import merge_swarm_into_intel
    swarm = {
        "intel": {
            "wikipedia_url": {"value": "https://en.wikipedia.org/wiki/X",
                               "confidence": "high", "sources": ["wikipedia"]},
            "wikidata_qid": {"value": "Q42",
                              "confidence": "high", "sources": ["wikidata"]},
            "wikidata_url": {"value": "https://www.wikidata.org/wiki/Q42",
                              "confidence": "high", "sources": ["wikidata"]},
        },
        "application_kit": {},
    }
    out = merge_swarm_into_intel({}, swarm)
    co = out["company_overview"]
    assert co["wikipedia_url"] == "https://en.wikipedia.org/wiki/X"
    assert co["wikidata_qid"] == "Q42"
    assert co["wikidata_url"] == "https://www.wikidata.org/wiki/Q42"


# ─── streaming events (Phase A — coordinator emits via agent_events) ──

@pytest.mark.asyncio
async def test_coordinator_emits_swarm_layer_and_provider_events():
    """Coordinator emits a structured event stream: swarm.start → layer1
    start/complete → layer2 start/complete → fusion start/complete →
    mapper start/complete → swarm.complete, plus tool_call/tool_result
    per provider."""
    from ai_engine.agent_events import event_emitter_scope

    captured: list[tuple[str, dict]] = []

    async def _capture(event_name: str, payload: dict) -> None:
        captured.append((event_name, payload))

    coord = ReconSwarmCoordinator(cache=_MemoryCache())
    req = ReconSwarmRequest(company="Acme", budget_seconds=15)

    with event_emitter_scope(_capture):
        await coord.run(req)
        # event firing is fire-and-forget via loop.create_task — drain
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    names = [n for n, _ in captured]
    # Swarm bookends
    assert "phase" in names
    phases = [
        (p["phase"], p["status"])
        for n, p in captured
        if n == "phase"
    ]
    assert ("swarm", "running") in phases
    assert ("swarm", "completed") in phases
    assert ("layer1", "running") in phases
    assert ("layer1", "completed") in phases
    assert ("layer2", "running") in phases
    assert ("layer2", "completed") in phases
    assert ("fusion", "running") in phases
    assert ("fusion", "completed") in phases
    assert ("mapper", "running") in phases
    assert ("mapper", "completed") in phases

    # Per-provider tool events: every default stub provider should emit
    # a tool_call followed by a tool_result.
    tool_calls = [p["tool"] for n, p in captured if n == "tool_call"]
    tool_results = [p["tool"] for n, p in captured if n == "tool_result"]
    # Default stubs include crunchbase + linkedin + glassdoor etc.
    assert "crunchbase_stub" in tool_calls
    assert "crunchbase_stub" in tool_results
    # All tool calls produced a matching result
    assert len(tool_results) == len(tool_calls)


@pytest.mark.asyncio
async def test_coordinator_emits_failed_tool_result_when_provider_raises():
    from ai_engine.agent_events import event_emitter_scope

    class _Broken:
        name = "broken_test"
        layer = 1

        async def fetch(self, **_):
            raise RuntimeError("boom")

    captured: list[tuple[str, dict]] = []

    async def _capture(event_name: str, payload: dict) -> None:
        captured.append((event_name, payload))

    coord = ReconSwarmCoordinator(
        layer1=[_Broken()], layer2=[], cache=_MemoryCache(),
    )
    with event_emitter_scope(_capture):
        await coord.run(ReconSwarmRequest(company="Acme", budget_seconds=10))
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    broken_results = [
        p for n, p in captured
        if n == "tool_result" and p.get("tool") == "broken_test"
    ]
    assert broken_results, "expected a tool_result event for failing provider"
    assert broken_results[-1]["status"] == "failed"
    assert "boom" in (broken_results[-1].get("error") or "")


@pytest.mark.asyncio
async def test_coordinator_emits_cache_hit_event_on_warm_cache():
    from ai_engine.agent_events import event_emitter_scope

    cache = _MemoryCache()
    coord = ReconSwarmCoordinator(cache=cache)
    req = ReconSwarmRequest(company="Acme", budget_seconds=10)

    # Warm
    await coord.run(req)

    captured: list[tuple[str, dict]] = []

    async def _capture(event_name: str, payload: dict) -> None:
        captured.append((event_name, payload))

    with event_emitter_scope(_capture):
        report = await coord.run(req)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    assert report.cache_hit is True
    assert any(n == "cache_hit" for n, _ in captured)
    # On cache hit we should NOT emit layer1/layer2 phases.
    layer_phases = [
        (p["phase"], p["status"]) for n, p in captured
        if n == "phase" and p["phase"] in {"layer1", "layer2", "fusion", "mapper"}
    ]
    assert layer_phases == []
    # But swarm.completed should still be emitted.
    swarm_phases = [
        (p["phase"], p["status"]) for n, p in captured
        if n == "phase" and p["phase"] == "swarm"
    ]
    assert ("swarm", "running") in swarm_phases
    assert ("swarm", "completed") in swarm_phases


def test_emit_phase_helper_is_noop_without_emitter():
    """emit_phase must be safe to call when no SSE bridge is bound."""
    from ai_engine.agent_events import emit_phase
    # Should not raise.
    emit_phase("swarm", "running", agent="recon_swarm", message="x")
