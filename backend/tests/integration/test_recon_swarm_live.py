"""Network-gated live integration tests for real Recon Swarm providers.

These tests are SKIPPED by default. To run them locally:

    RUN_RECON_LIVE=1 pytest -q tests/integration/test_recon_swarm_live.py

They make real outbound calls to:
  - https://www.sec.gov  (SEC EDGAR — public, free, ToS-permits)
  - https://api.github.com/orgs/openai (public REST API)
  - https://news.google.com/rss (public RSS)
  - https://hn.algolia.com (HN Algolia search API — free, no auth)
  - https://www.reddit.com (Reddit search.json — free, no auth)
  - https://api.stackexchange.com (Stack Exchange API — free, no auth)
  - https://export.arxiv.org (arXiv API — free, no auth)
  - https://en.wikipedia.org (Wikipedia REST API — free, no auth)

Each test is best-effort: a transient network/rate-limit failure logs
and is marked xfail rather than blocking CI.
"""
from __future__ import annotations

import os

import pytest

from ai_engine.agents.sub_agents.recon_swarm import (
    GitHubProvider,
    GoogleNewsProvider,
    HackerNewsProvider,
    RedditProvider,
    SECEdgarProvider,
    StackExchangeProvider,
    ArxivProvider,
    WikipediaProvider,
)


pytestmark = pytest.mark.skipif(
    (os.getenv("RUN_RECON_LIVE") or "").lower() not in {"1", "true", "yes"},
    reason="Live network tests skipped — set RUN_RECON_LIVE=1 to enable.",
)


@pytest.mark.asyncio
async def test_sec_edgar_live_apple_lookup():
    p = SECEdgarProvider()
    r = await p.fetch(company="Apple")
    if not r.success:
        pytest.xfail(f"SEC EDGAR live call failed: {r.error}")
    assert r.raw["is_public"] is True
    assert r.raw["ticker"] == "AAPL"
    assert "Apple" in r.raw.get("legal_name", "")


@pytest.mark.asyncio
async def test_github_live_openai_org_lookup():
    p = GitHubProvider()
    r = await p.fetch(company="openai")
    if not r.success:
        pytest.xfail(f"GitHub live call failed: {r.error}")
    assert r.raw["github_orgs"] == ["openai"]
    assert r.raw["repo_count"] >= 1
    assert isinstance(r.raw.get("languages"), list)


@pytest.mark.asyncio
async def test_google_news_live_stripe_search():
    p = GoogleNewsProvider(max_items=3)
    r = await p.fetch(company="Stripe payments")
    if not r.success:
        pytest.xfail(f"Google News live call failed: {r.error}")
    items = r.raw.get("recent_news", [])
    # Google may legitimately return zero items for some queries; only
    # require shape if any items came back.
    for it in items:
        assert "title" in it and it["title"]
        assert "source" in it


@pytest.mark.asyncio
async def test_hackernews_live_openai_search():
    p = HackerNewsProvider(max_items=3)
    r = await p.fetch(company="OpenAI")
    if not r.success:
        pytest.xfail(f"HN Algolia live call failed: {r.error}")
    items = r.raw.get("recent_news", [])
    for it in items:
        assert it["source"] == "Hacker News"
        assert "title" in it and it["title"]
        assert isinstance(it.get("points", 0), int)


@pytest.mark.asyncio
async def test_wikipedia_live_apple_lookup():
    p = WikipediaProvider()
    r = await p.fetch(company="Apple Inc.")
    if not r.success:
        pytest.xfail(f"Wikipedia live call failed: {r.error}")
    assert "Apple" in (r.raw.get("legal_name") or "")
    # Description text should mention Apple or technology somewhere.
    desc = (r.raw.get("description") or "").lower()
    assert "apple" in desc or "technology" in desc


@pytest.mark.asyncio
async def test_reddit_live_openai_search():
    p = RedditProvider(max_items=3)
    r = await p.fetch(company="OpenAI")
    if not r.success:
        pytest.xfail(f"Reddit live call failed: {r.error}")
    items = r.raw.get("recent_news", [])
    for it in items:
        assert it["source"].startswith("Reddit")
        assert "title" in it and it["title"]
        assert isinstance(it.get("score", 0), int)


@pytest.mark.asyncio
async def test_stackexchange_live_react_search():
    p = StackExchangeProvider(max_items=3)
    r = await p.fetch(company="react")
    if not r.success:
        pytest.xfail(f"Stack Exchange live call failed: {r.error}")
    items = r.raw.get("recent_news", [])
    for it in items:
        assert it["source"] == "Stack Overflow"
        assert "title" in it and it["title"]
        assert isinstance(it.get("score", 0), int)
        assert isinstance(it.get("tags", []), list)


@pytest.mark.asyncio
async def test_arxiv_live_transformer_search():
    p = ArxivProvider(max_items=3)
    r = await p.fetch(company="transformer")
    if not r.success:
        pytest.xfail(f"arXiv live call failed: {r.error}")
    papers = r.raw.get("research_papers", [])
    assert len(papers) >= 1
    for it in papers:
        assert it["source"] == "arXiv"
        assert it["title"]
        assert it["url"].startswith("http://arxiv.org/abs/")
        assert isinstance(it.get("authors", []), list)


@pytest.mark.asyncio
async def test_wikidata_provider_live_apple():
    from ai_engine.agents.sub_agents.recon_swarm.providers import WikidataProvider
    p = WikidataProvider()
    r = await p.fetch(company="Apple Inc.")
    assert r.success is True, f"wikidata failed: {r.error}"
    assert r.raw.get("wikidata_qid", "").startswith("Q")
    # Apple was founded 1976 — extremely stable Wikidata fact
    fy = r.raw.get("founded_year")
    assert fy is None or 1970 < fy < 2000
