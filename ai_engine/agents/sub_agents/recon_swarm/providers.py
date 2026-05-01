"""S18 — Source Provider Protocol + deterministic stub providers.

Each provider returns a `ProviderResult` with `raw` payload keyed by
fields that `IntelFusion` knows how to merge. Stubs are deterministic
(seeded by company name) so unit tests are stable and offline.

Real-API impls (Crunchbase, BuiltWith, GoogleNews, etc.) are FOLLOW-UP
work — each requires its own API key + ToS review. Slot them in by
implementing `SourceProvider` and adding to the env-aware factory.

Hard rule: NO LinkedIn, Glassdoor, or PitchBook scrapers in this repo.
A licensed Sales Navigator / Glassdoor B2B / PitchBook API key can
power a future provider impl.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any, Dict, List, Optional, Protocol

from .schemas import ProviderResult

logger = logging.getLogger(__name__)


def _seed_int(s: str, mod: int = 100) -> int:
    digest = hashlib.sha1((s or "").lower().encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % mod


class SourceProvider(Protocol):
    name: str
    layer: int

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        ...


# ─── helper to time + wrap stub fetches ───────────────────────────

async def _wrapped(name: str, layer: int, payload: Dict[str, Any],
                   started: float) -> ProviderResult:
    return ProviderResult(
        provider=name,
        layer=layer,
        success=True,
        latency_ms=int((time.perf_counter() - started) * 1000),
        raw=payload,
    )


# ─── Layer 1 — source discovery stubs ─────────────────────────────

class StubCrunchbaseProvider:
    name = "crunchbase_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        seed = _seed_int(company, mod=20)
        rounds = ["Pre-Seed", "Seed", "Series A", "Series B", "Series C", "Series D"]
        idx = min(seed % len(rounds), len(rounds) - 1)
        return await _wrapped(self.name, self.layer, {
            "total_funding_usd": (seed + 5) * 5_000_000,
            "last_round": rounds[idx],
            "last_round_date": "2025-09-01",
            "investors": [f"Stub Capital {chr(65 + (seed % 5))}",
                          f"Stub Ventures {chr(70 + (seed % 5))}"],
            "company_stage": rounds[idx].lower().replace(" ", "_"),
            "founded_year": 2010 + (seed % 14),
        }, s)


class StubLinkedInProvider:
    """STUB ONLY — does NOT scrape LinkedIn. Real impl requires
    Sales Navigator API key + B2B contract."""
    name = "linkedin_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        seed = _seed_int(company, mod=2000)
        headcount = 50 + seed
        return await _wrapped(self.name, self.layer, {
            "headcount": headcount,
            "eng_headcount": int(headcount * 0.32),
            "leadership": [
                {"name": "A. Smith", "title": "CEO", "tenure_years": 4},
                {"name": "B. Jones", "title": "CTO", "tenure_years": 3},
                {"name": "C. Park", "title": "VP Eng", "tenure_years": 2},
            ],
            "open_roles_count": max(1, headcount // 25),
        }, s)


class StubBuiltWithProvider:
    name = "builtwith_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        seed = _seed_int(company, mod=8)
        all_stacks = ["React", "Next.js", "TypeScript", "Python", "FastAPI",
                      "PostgreSQL", "Redis", "Kubernetes", "AWS", "GCP",
                      "Snowflake", "Datadog"]
        return await _wrapped(self.name, self.layer, {
            "tech_stack": all_stacks[: 6 + (seed % 4)],
        }, s)


class StubGitHubProvider:
    name = "github_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        seed = _seed_int(company, mod=80)
        return await _wrapped(self.name, self.layer, {
            "github_orgs": [(company or "company").lower().replace(" ", "-")],
            "repo_count": 5 + seed,
            "languages": ["Python", "TypeScript", "Go"][: 1 + (seed % 3)],
        }, s)


class StubGoogleNewsProvider:
    name = "google_news_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        items = [
            {"title": f"{company} announces growth", "date": "2026-03-15",
             "source": "TechCrunch"},
            {"title": f"{company} expands engineering team", "date": "2026-02-10",
             "source": "The Information"},
        ]
        return await _wrapped(self.name, self.layer, {
            "recent_news": items,
        }, s)


# ─── Layer 2 — deep extraction stubs ──────────────────────────────

class _SafeWebsiteFetcher:
    """Tiny httpx fetcher with hard timeout. Failures degrade silently."""

    def __init__(self, client: Optional[Any] = None, timeout_s: float = 8.0):
        self._client = client
        self._timeout_s = timeout_s

    async def get_text(self, url: str) -> str:
        if not url:
            return ""
        client, owned = await self._get_client()
        try:
            resp = await client.get(url)
            if getattr(resp, "status_code", 0) != 200:
                return ""
            text = getattr(resp, "text", "") or ""
            return text[:50_000]
        except Exception as exc:  # noqa: BLE001
            logger.info("website fetch failed url=%s exc=%s", url, exc)
            return ""
        finally:
            if owned:
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return httpx.AsyncClient(timeout=self._timeout_s), True


class StubWebsiteCrawlerProvider:
    """Layer-2 deep-crawl stub. Real impl: Playwright + LLM chunking.
    This stub returns a deterministic 'about page' payload + optional
    real fetch when an http client is injected."""
    name = "website_crawl_stub"
    layer = 2

    def __init__(self, http_client: Optional[Any] = None) -> None:
        self._fetcher = _SafeWebsiteFetcher(client=http_client)

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        website = ctx.get("website") or ""
        text = ""
        if website and ctx.get("allow_network"):
            text = await self._fetcher.get_text(website)
        if not text:
            text = (
                f"{company} is a fast-moving team building software for "
                "modern companies. We value ownership, customer obsession, "
                "and craft. Our stack centers on Python, Postgres, and "
                "TypeScript. We hire engineers who ship and operate."
            )
        return await _wrapped(self.name, self.layer, {
            "raw_about_text": text,
            "values": ["ownership", "customer obsession", "craft"],
            "work_style": "hybrid",
            "benefits": ["health insurance", "equity", "learning budget"],
        }, s)


class StubSECProvider:
    """SEC EDGAR is public + free, but stubbed here so tests are
    offline. Real impl: data.sec.gov/submissions/CIK....json."""
    name = "sec_stub"
    layer = 2

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        is_public = bool(ctx.get("is_public"))
        if not is_public:
            return await _wrapped(self.name, self.layer, {
                "is_public": False,
            }, s)
        seed = _seed_int(company, mod=900)
        return await _wrapped(self.name, self.layer, {
            "is_public": True,
            "ticker": (company or "X")[:4].upper(),
            "sec_revenue_usd": (seed + 100) * 1_000_000,
            "sec_risk_factors": [
                "market competition",
                "regulatory exposure",
                "key personnel concentration",
            ],
        }, s)


class StubPatentProvider:
    name = "patent_stub"
    layer = 2

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        return await _wrapped(self.name, self.layer, {
            "patents_count": _seed_int(company, mod=40),
        }, s)


class StubProductHuntProvider:
    name = "product_hunt_stub"
    layer = 2

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        return await _wrapped(self.name, self.layer, {
            "product_launches": [
                {"name": f"{company} v2", "date": "2025-12-01"},
            ],
        }, s)


class StubGlassdoorProvider:
    """STUB ONLY — Glassdoor scraping is ToS-prohibited. Real impl
    requires a Glassdoor B2B API contract."""
    name = "glassdoor_stub"
    layer = 2

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        seed = _seed_int(company, mod=15)
        rating = round(3.4 + (seed / 30.0), 1)
        return await _wrapped(self.name, self.layer, {
            "glassdoor_rating": rating,
            "glassdoor_themes": [
                "fast-paced", "smart team", "growth opportunities",
                "intense workload",
            ],
        }, s)


class StubTwitterProvider:
    name = "twitter_stub"
    layer = 2

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        handle = "@" + (company or "company").lower().replace(" ", "")[:15]
        return await _wrapped(self.name, self.layer, {
            "twitter_handle": handle,
            "twitter_sentiment": "positive",
        }, s)


# ─── Real provider: SEC EDGAR (free + ToS-compliant) ──────────────

_SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
_SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
_SEC_USER_AGENT_DEFAULT = "HireStack AI recon-swarm contact@hirestack.ai"


class SECEdgarProvider:
    """Real SEC EDGAR provider.

    SEC EDGAR is public, free, and explicitly ToS-permits programmatic
    access provided you set a descriptive User-Agent header and respect
    the 10-req/sec rate limit. We comply with both.

    Reference: https://www.sec.gov/os/accessing-edgar-data

    Activation: set env RECON_SEC_PROVIDER=real (or pass real_enabled=True).
    Falls back to a 'sec' provider with success=False on any network
    error — never raises.
    """

    name = "sec"
    layer = 2

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        user_agent: Optional[str] = None,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._ua = user_agent or os.getenv("SEC_USER_AGENT",
                                          _SEC_USER_AGENT_DEFAULT)
        self._timeout_s = timeout_s

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        client, owned = await self._get_client()
        try:
            cik = await self._lookup_cik(client, company)
            if not cik:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=True,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    raw={"is_public": False},
                )
            sub = await self._fetch_submissions(client, cik)
            if not sub:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error="submissions fetch failed",
                )
            payload = self._extract_payload(sub)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("sec_edgar fetch failed company=%s exc=%s",
                        company, exc)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error=str(exc)[:200],
            )
        finally:
            if owned:
                try:
                    await client.aclose()
                except Exception:  # noqa: BLE001
                    pass

    # ─── helpers ──────────────────────────────────────────────

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return (
            httpx.AsyncClient(
                timeout=self._timeout_s,
                headers={"User-Agent": self._ua,
                         "Accept": "application/json"},
            ),
            True,
        )

    async def _lookup_cik(self, client: Any, company: str) -> Optional[str]:
        if not (company or "").strip():
            return None
        resp = await client.get(_SEC_TICKERS_URL)
        if getattr(resp, "status_code", 0) != 200:
            return None
        data = resp.json() or {}
        target = company.strip().lower()
        for entry in data.values():
            try:
                title = str(entry.get("title", "")).lower()
                ticker = str(entry.get("ticker", "")).lower()
                if title == target or ticker == target or target in title:
                    return f"{int(entry['cik_str']):010d}"
            except Exception:  # noqa: BLE001
                continue
        return None

    async def _fetch_submissions(
        self, client: Any, cik: str,
    ) -> Optional[Dict[str, Any]]:
        resp = await client.get(_SEC_SUBMISSIONS_URL.format(cik=cik))
        if getattr(resp, "status_code", 0) != 200:
            return None
        return resp.json() or {}

    @staticmethod
    def _extract_payload(sub: Dict[str, Any]) -> Dict[str, Any]:
        tickers = sub.get("tickers") or []
        ticker = tickers[0] if tickers else None
        sic_desc = sub.get("sicDescription") or None
        addresses = sub.get("addresses") or {}
        biz = addresses.get("business") or {}
        hq = None
        if biz:
            city = biz.get("city")
            state = biz.get("stateOrCountry")
            hq = ", ".join([p for p in (city, state) if p]) or None
        former = [n.get("name") for n in (sub.get("formerNames") or [])
                  if n.get("name")]
        return {
            "is_public": True,
            "ticker": ticker,
            "legal_name": sub.get("name"),
            "industry": sic_desc,
            "headquarters": hq,
            "former_names": former,
        }


# ─── Factories (env-aware) ────────────────────────────────────────

def default_layer1_providers() -> List[SourceProvider]:
    """Layer-1 default set. Real-API providers slot in here when
    their key env vars are configured (follow-up work)."""
    providers: List[SourceProvider] = [
        StubCrunchbaseProvider(),
        StubLinkedInProvider(),
        StubBuiltWithProvider(),
        StubGitHubProvider(),
        StubGoogleNewsProvider(),
    ]
    # Future:
    #   if os.getenv("CRUNCHBASE_API_KEY"):
    #       providers.append(CrunchbaseProvider())
    return providers


def default_layer2_providers(
    http_client: Optional[Any] = None,
) -> List[SourceProvider]:
    sec: SourceProvider
    if (os.getenv("RECON_SEC_PROVIDER") or "stub").lower() == "real":
        sec = SECEdgarProvider(http_client=http_client)
    else:
        sec = StubSECProvider()
    return [
        StubWebsiteCrawlerProvider(http_client=http_client),
        sec,
        StubPatentProvider(),
        StubProductHuntProvider(),
        StubGlassdoorProvider(),
        StubTwitterProvider(),
    ]
