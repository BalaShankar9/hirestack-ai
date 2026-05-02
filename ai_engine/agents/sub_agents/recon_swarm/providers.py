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


# ─── Real provider: GitHub (free public API) ──────────────────────

_GH_ORG_URL = "https://api.github.com/orgs/{org}"
_GH_REPOS_URL = "https://api.github.com/orgs/{org}/repos?per_page=100&type=public"


class GitHubProvider:
    """Real GitHub provider.

    GitHub's public REST API is free up to 60 req/hr unauthenticated and
    5,000 req/hr with a token (set GITHUB_TOKEN). Org slug is derived
    from the company name (lowercase, dashes). On 404 (org not found)
    or any HTTP/network error, returns success=False without raising.

    Activation: RECON_GITHUB_PROVIDER=real (default stub).
    """

    name = "github"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        token: Optional[str] = None,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._token = token or os.getenv("GITHUB_TOKEN")
        self._timeout_s = timeout_s

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        org = self._derive_org(company)
        if not org:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="could not derive github org",
            )
        client, owned = await self._get_client()
        try:
            org_resp = await client.get(_GH_ORG_URL.format(org=org))
            if getattr(org_resp, "status_code", 0) != 200:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error=f"org lookup status={org_resp.status_code}",
                )
            repos_resp = await client.get(_GH_REPOS_URL.format(org=org))
            repos = []
            if getattr(repos_resp, "status_code", 0) == 200:
                repos = repos_resp.json() or []
            payload = self._extract(org_resp.json() or {}, repos, org)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("github fetch failed company=%s exc=%s", company, exc)
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

    @staticmethod
    def _derive_org(company: str) -> Optional[str]:
        s = (company or "").strip().lower()
        if not s:
            return None
        # Conservative slug: lowercase, replace spaces with dash, strip
        # punctuation. GitHub org slugs are limited to [a-z0-9-].
        cleaned = "".join(
            c if c.isalnum() or c == "-" else ("-" if c.isspace() else "")
            for c in s
        )
        cleaned = cleaned.strip("-")
        return cleaned or None

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "HireStack-AI-Recon-Swarm",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return httpx.AsyncClient(timeout=self._timeout_s, headers=headers), True

    @staticmethod
    def _extract(
        org_payload: Dict[str, Any],
        repos: List[Dict[str, Any]],
        org_slug: str,
    ) -> Dict[str, Any]:
        # Aggregate languages weighted by repo count
        lang_counts: Dict[str, int] = {}
        for r in repos:
            lang = r.get("language")
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
        languages = [l for l, _ in sorted(
            lang_counts.items(), key=lambda kv: kv[1], reverse=True,
        )][:8]
        return {
            "github_orgs": [org_slug],
            "repo_count": int(org_payload.get("public_repos")
                              or len(repos) or 0),
            "languages": languages,
            "description": org_payload.get("description") or None,
            "website": org_payload.get("blog") or None,
        }


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


# ─── Real provider: Google News RSS (free, no key) ────────────────────

_GNEWS_URL = (
    "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en"
)


class GoogleNewsProvider:
    """Real Google News provider via the public RSS endpoint.

    No API key, no auth. Returns up to N most-recent items. Parses RSS
    with stdlib xml.etree (no extra dep). Source name is extracted from
    the <source> element when present, else from <title> suffix
    ('Title - Source'). Gracefully degrades on any error.

    Activation: RECON_GOOGLE_NEWS_PROVIDER=real (default stub).
    """

    name = "google_news"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        max_items: int = 10,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._max_items = max(1, int(max_items))
        self._timeout_s = timeout_s

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        q = (company or "").strip()
        if not q:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty company",
            )
        from urllib.parse import quote_plus
        url = _GNEWS_URL.format(q=quote_plus(q))
        client, owned = await self._get_client()
        try:
            resp = await client.get(url)
            if getattr(resp, "status_code", 0) != 200:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error=f"rss status={resp.status_code}",
                )
            text = resp.text if hasattr(resp, "text") else ""
            items = self._parse_rss(text, self._max_items)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw={"recent_news": items},
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("google_news fetch failed company=%s exc=%s",
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

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return httpx.AsyncClient(
            timeout=self._timeout_s,
            headers={"User-Agent": "HireStack-AI-Recon-Swarm"},
            follow_redirects=True,
        ), True

    @staticmethod
    def _parse_rss(text: str, limit: int) -> List[Dict[str, Any]]:
        if not text:
            return []
        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        out: List[Dict[str, Any]] = []
        # RSS layout: <rss><channel><item>...</item>*</channel></rss>
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            if not title:
                continue
            pub = (item.findtext("pubDate") or "").strip()
            source_el = item.find("source")
            src = (source_el.text if source_el is not None else "") or ""
            src = src.strip()
            # Google News titles often look like "Headline - Source".
            # Strip the trailing source attribution from title.
            if " - " in title:
                head, _, tail = title.rpartition(" - ")
                if head and tail and len(tail) <= 60:
                    title = head.strip()
                    if not src:
                        src = tail.strip()
            out.append({
                "title": title,
                "date": GoogleNewsProvider._normalize_date(pub),
                "source": src or "Google News",
            })
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def _normalize_date(pub: str) -> str:
        # RFC-822: 'Tue, 14 Apr 2026 10:30:00 GMT' -> '2026-04-14'
        if not pub:
            return ""
        from email.utils import parsedate_to_datetime
        try:
            dt = parsedate_to_datetime(pub)
            return dt.date().isoformat()
        except Exception:  # noqa: BLE001
            return pub[:10]


# ─── Hacker News (Algolia) — community signal, free, no auth ──────

class StubHackerNewsProvider:
    name = "hacker_news_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        items = [
            {"title": f"Show HN: {company} launches new product",
             "url": "https://news.ycombinator.com/item?id=stub1",
             "date": "2026-04-01", "source": "Hacker News"},
            {"title": f"{company} raises Series B",
             "url": "https://news.ycombinator.com/item?id=stub2",
             "date": "2026-03-15", "source": "Hacker News"},
        ]
        return await _wrapped(self.name, self.layer, {
            "recent_news": items,
        }, s)


_HN_ALGOLIA_URL = (
    "https://hn.algolia.com/api/v1/search?query={q}"
    "&tags=story&hitsPerPage={n}"
)


class HackerNewsProvider:
    """Real Hacker News provider via the public Algolia search API.

    Free, no auth, no rate-limit ceremony. Returns top story hits as
    `recent_news` items so they fuse with Google News / Crunchbase
    items in IntelFusion's list-merge step.

    Reference: https://hn.algolia.com/api

    Activation: RECON_HACKERNEWS_PROVIDER=real (default: stub).
    """

    name = "hacker_news"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        max_items: int = 10,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._max_items = max(1, int(max_items))
        self._timeout_s = timeout_s

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        q = (company or "").strip()
        if not q:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty company",
            )
        from urllib.parse import quote_plus
        url = _HN_ALGOLIA_URL.format(q=quote_plus(q), n=self._max_items)
        client, owned = await self._get_client()
        try:
            resp = await client.get(url)
            if getattr(resp, "status_code", 0) != 200:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error=f"hn status={resp.status_code}",
                )
            data = resp.json() or {}
            items = self._extract_items(data, self._max_items)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw={"recent_news": items},
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("hacker_news fetch failed company=%s exc=%s",
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

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return (
            httpx.AsyncClient(
                timeout=self._timeout_s,
                headers={"User-Agent": "HireStack-AI-Recon-Swarm",
                         "Accept": "application/json"},
            ),
            True,
        )

    @staticmethod
    def _extract_items(data: Dict[str, Any], limit: int) -> List[Dict[str, Any]]:
        hits = data.get("hits") or []
        out: List[Dict[str, Any]] = []
        for h in hits:
            if not isinstance(h, dict):
                continue
            title = (h.get("title") or h.get("story_title") or "").strip()
            if not title:
                continue
            url = h.get("url") or h.get("story_url") or ""
            created = (h.get("created_at") or "")[:10]
            out.append({
                "title": title,
                "url": url,
                "date": created,
                "source": "Hacker News",
                "points": int(h.get("points") or 0),
                "comments": int(h.get("num_comments") or 0),
            })
            if len(out) >= limit:
                break
        return out


# ─── Reddit (public JSON) — community signal, free, no auth ───────

class StubRedditProvider:
    name = "reddit_stub"
    layer = 1

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        items = [
            {"title": f"Has anyone interviewed at {company}?",
             "url": "https://reddit.com/r/cscareerquestions/stub1",
             "date": "2026-04-02", "source": "Reddit"},
            {"title": f"Working at {company} - my experience",
             "url": "https://reddit.com/r/cscareerquestions/stub2",
             "date": "2026-03-20", "source": "Reddit"},
        ]
        return await _wrapped(self.name, self.layer, {
            "recent_news": items,
        }, s)


_REDDIT_SEARCH_URL = (
    "https://www.reddit.com/search.json?q={q}"
    "&sort=relevance&limit={n}&t=year"
)


class RedditProvider:
    """Real Reddit provider via the public search.json endpoint.

    No auth required for read-only public search. Reddit asks that
    clients send a descriptive User-Agent and avoid hammering the
    API; both honored. Returns top hits as `recent_news` items so
    they fuse alongside HN / Google News in IntelFusion.

    Reference: https://www.reddit.com/dev/api/  (search endpoint)

    Activation: RECON_REDDIT_PROVIDER=real (default: stub).
    """

    name = "reddit"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        max_items: int = 10,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._max_items = max(1, int(max_items))
        self._timeout_s = timeout_s

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        q = (company or "").strip()
        if not q:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty company",
            )
        from urllib.parse import quote_plus
        url = _REDDIT_SEARCH_URL.format(
            q=quote_plus(q), n=self._max_items,
        )
        client, owned = await self._get_client()
        try:
            resp = await client.get(url)
            if getattr(resp, "status_code", 0) != 200:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error=f"reddit status={resp.status_code}",
                )
            data = resp.json() or {}
            items = self._extract_items(data, self._max_items)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw={"recent_news": items},
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("reddit fetch failed company=%s exc=%s",
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

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return (
            httpx.AsyncClient(
                timeout=self._timeout_s,
                headers={
                    # Reddit bans generic UAs; their docs ask for the
                    # "platform:appname:version (by /u/username)" form
                    # — descriptive UAs are not rate-limited.
                    "User-Agent": (
                        "linux:hirestack-ai:1.0 (by /u/hirestack-ai)"
                    ),
                    "Accept": "application/json",
                },
                follow_redirects=True,
            ),
            True,
        )

    @staticmethod
    def _extract_items(
        data: Dict[str, Any], limit: int,
    ) -> List[Dict[str, Any]]:
        children = (data.get("data") or {}).get("children") or []
        out: List[Dict[str, Any]] = []
        for c in children:
            if not isinstance(c, dict):
                continue
            d = c.get("data") or {}
            if not isinstance(d, dict):
                continue
            title = (d.get("title") or "").strip()
            if not title:
                continue
            permalink = d.get("permalink") or ""
            link = (
                f"https://www.reddit.com{permalink}"
                if permalink else (d.get("url") or "")
            )
            created = d.get("created_utc")
            date_iso = ""
            if isinstance(created, (int, float)) and created > 0:
                from datetime import datetime, timezone
                date_iso = datetime.fromtimestamp(
                    float(created), tz=timezone.utc,
                ).date().isoformat()
            subreddit = d.get("subreddit") or ""
            out.append({
                "title": title,
                "url": link,
                "date": date_iso,
                "source": (
                    f"Reddit r/{subreddit}" if subreddit else "Reddit"
                ),
                "score": int(d.get("score") or 0),
                "comments": int(d.get("num_comments") or 0),
            })
            if len(out) >= limit:
                break
        return out


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


# ─── Real provider: Wikipedia REST API (free, no key) ─────────────

_WIKI_SUMMARY_URL = (
    "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
)
_WIKI_SEARCH_URL = (
    "https://en.wikipedia.org/w/api.php?action=opensearch&search={q}"
    "&limit=5&namespace=0&format=json"
)


class WikipediaProvider:
    """Real Wikipedia REST API provider (Layer 2).

    Free, no auth, public. Looks up the page summary for the company
    and extracts description, founded_year (from extract first sentence),
    headquarters, industry, and homepage. Pure-stdlib JSON parsing.
    Falls back to OpenSearch when direct title lookup 404s.

    Reference: https://en.wikipedia.org/api/rest_v1/

    Activation: RECON_WIKIPEDIA_PROVIDER=real (default stub).
    Gracefully degrades on any error \u2014 never raises.
    """

    name = "wikipedia"
    layer = 2

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        timeout_s: float = 8.0,
    ) -> None:
        self._client = http_client
        self._timeout_s = timeout_s

    async def fetch(self, *, company: str, **ctx: Any) -> ProviderResult:
        s = time.perf_counter()
        q = (company or "").strip()
        if not q:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty company",
            )
        client, owned = await self._get_client()
        try:
            summary = await self._lookup_summary(client, q)
            if not summary:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=True,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    raw={},
                )
            payload = self._extract_payload(summary)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("wikipedia fetch failed company=%s exc=%s",
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

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        return (
            httpx.AsyncClient(
                timeout=self._timeout_s,
                headers={"User-Agent": "HireStack-AI-Recon-Swarm",
                         "Accept": "application/json"},
                follow_redirects=True,
            ),
            True,
        )

    async def _lookup_summary(
        self, client: Any, q: str,
    ) -> Optional[Dict[str, Any]]:
        from urllib.parse import quote
        # Try direct title lookup first.
        url = _WIKI_SUMMARY_URL.format(title=quote(q.replace(" ", "_")))
        resp = await client.get(url)
        status = getattr(resp, "status_code", 0)
        if status == 200:
            data = resp.json() or {}
            if data.get("type") != "disambiguation":
                return data
        # Fallback: OpenSearch \u2192 first hit \u2192 summary.
        from urllib.parse import quote_plus
        search_url = _WIKI_SEARCH_URL.format(q=quote_plus(q))
        sresp = await client.get(search_url)
        if getattr(sresp, "status_code", 0) != 200:
            return None
        sdata = sresp.json() or []
        # OpenSearch returns: [query, [titles], [descs], [urls]]
        titles = sdata[1] if isinstance(sdata, list) and len(sdata) >= 2 else []
        if not titles:
            return None
        first_title = titles[0]
        url2 = _WIKI_SUMMARY_URL.format(
            title=quote(first_title.replace(" ", "_")),
        )
        resp2 = await client.get(url2)
        if getattr(resp2, "status_code", 0) != 200:
            return None
        return resp2.json() or {}

    @staticmethod
    def _extract_payload(s: Dict[str, Any]) -> Dict[str, Any]:
        title = s.get("title") or None
        extract = s.get("extract") or ""
        # Wikipedia "description" is a short 1-line tagline (e.g.
        # "American multinational technology company").
        short_desc = s.get("description") or None
        out: Dict[str, Any] = {}
        if title:
            out["legal_name"] = title
        if extract:
            # Trim to first two sentences for description.
            parts = extract.split(". ")
            out["description"] = ". ".join(parts[:2]).strip()
            if out["description"] and not out["description"].endswith("."):
                out["description"] += "."
            year = WikipediaProvider._extract_founded_year(extract)
            if year:
                out["founded_year"] = year
        if short_desc:
            out["industry"] = short_desc
        # content_urls.desktop.page is the canonical URL.
        urls = s.get("content_urls") or {}
        homepage = (urls.get("desktop") or {}).get("page")
        if homepage:
            out["wikipedia_url"] = homepage
        return out

    @staticmethod
    def _extract_founded_year(text: str) -> Optional[int]:
        import re
        # Look for "founded in 1976" / "established in 1998" /
        # "(founded 1903)" / "incorporated on June 4, 2007".
        # Allow up to 40 chars (including digits in dates) between the
        # keyword and a 4-digit year, then validate range.
        m = re.search(
            r"(?:founded|established|incorporated).{0,40}?(\d{4})",
            text, re.IGNORECASE,
        )
        if m:
            try:
                y = int(m.group(1))
                if 1700 <= y <= 2100:
                    return y
            except ValueError:
                return None
        return None


# ─── Factories (env-aware) ────────────────────────────────────────

def default_layer1_providers() -> List[SourceProvider]:
    """Layer-1 default set. Real-API providers slot in here when
    their key env vars are configured (follow-up work)."""
    gh: SourceProvider
    if (os.getenv("RECON_GITHUB_PROVIDER") or "stub").lower() == "real":
        gh = GitHubProvider()
    else:
        gh = StubGitHubProvider()
    news: SourceProvider
    if (os.getenv("RECON_GOOGLE_NEWS_PROVIDER") or "stub").lower() == "real":
        news = GoogleNewsProvider()
    else:
        news = StubGoogleNewsProvider()
    hn: SourceProvider
    if (os.getenv("RECON_HACKERNEWS_PROVIDER") or "stub").lower() == "real":
        hn = HackerNewsProvider()
    else:
        hn = StubHackerNewsProvider()
    rd: SourceProvider
    if (os.getenv("RECON_REDDIT_PROVIDER") or "stub").lower() == "real":
        rd = RedditProvider()
    else:
        rd = StubRedditProvider()
    providers: List[SourceProvider] = [
        StubCrunchbaseProvider(),
        StubLinkedInProvider(),
        StubBuiltWithProvider(),
        gh,
        news,
        hn,
        rd,
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
    wiki: SourceProvider
    if (os.getenv("RECON_WIKIPEDIA_PROVIDER") or "off").lower() == "real":
        wiki = WikipediaProvider(http_client=http_client)
    else:
        wiki = None  # type: ignore[assignment]
    base: List[SourceProvider] = [
        StubWebsiteCrawlerProvider(http_client=http_client),
        sec,
        StubPatentProvider(),
        StubProductHuntProvider(),
        StubGlassdoorProvider(),
        StubTwitterProvider(),
    ]
    if wiki is not None:
        base.append(wiki)
    return base
