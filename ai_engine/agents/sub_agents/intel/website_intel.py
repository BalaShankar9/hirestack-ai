"""
WebsiteIntelAgent — deep company website crawl and extraction.

Fetches homepage, about page, team page, blog/news page, and product pages.
Extracts structured data: company description, leadership, tech signals,
product info, social proof, and content freshness indicators.
"""
from __future__ import annotations

import asyncio
import re
from typing import Any, Optional

import httpx
import structlog

from ai_engine.agents.sub_agents.base import SubAgent, SubAgentResult
from ai_engine.client import AIClient

logger = structlog.get_logger("hirestack.intel.website")

# Pages to crawl, in priority order
_PAGE_PATHS = [
    ("homepage", "/"),
    ("about", "/about"),
    ("about_us", "/about-us"),
    ("company", "/company"),
    ("team", "/team"),
    ("leadership", "/leadership"),
    ("blog", "/blog"),
    ("news", "/news"),
    ("press", "/press"),
    ("products", "/products"),
    ("solutions", "/solutions"),
    ("pricing", "/pricing"),
    ("values", "/values"),
    ("culture", "/culture"),
    ("engineering", "/engineering"),
    ("investors", "/investors"),
]

_USER_AGENT = "Mozilla/5.0 (compatible; HireStack-AI/2.0; Career Intelligence)"
_TIMEOUT = 6  # per-page timeout


def _guess_urls(company: str, company_url: Optional[str]) -> list[str]:
    """Generate candidate base URLs for the company (TLD enumeration fallback)."""
    urls: list[str] = []
    if company_url:
        urls.append(company_url.rstrip("/"))
    clean = re.sub(
        r"\s*(Inc|Ltd|LLC|Corp|Limited|PLC|GmbH|SA|AG|Co)\.?\s*$",
        "", company, flags=re.IGNORECASE,
    )
    clean = re.sub(r"[^a-zA-Z0-9]", "", clean).lower()
    if len(clean) >= 2:
        for tld in [".com", ".io", ".ai", ".co", ".dev", ".org"]:
            candidate = f"https://www.{clean}{tld}"
            if candidate not in urls:
                urls.append(candidate)
            candidate_no_www = f"https://{clean}{tld}"
            if candidate_no_www not in urls:
                urls.append(candidate_no_www)
    return urls


# Domains we never want to treat as the company's official site, even if
# they rank top in search results for the company name.
_DOMAIN_BLOCKLIST = {
    "linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com",
    "github.com", "crunchbase.com", "bloomberg.com", "glassdoor.com",
    "indeed.com", "ziprecruiter.com", "wikipedia.org", "youtube.com",
    "reddit.com", "medium.com", "forbes.com", "techcrunch.com",
    "pitchbook.com", "owler.com", "zoominfo.com", "rocketreach.co",
    "apollo.io", "similarweb.com",
}


def _domain_of(url: str) -> str:
    try:
        import urllib.parse as up
        host = up.urlparse(url).netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        return host
    except Exception:
        return ""


async def _discover_url_via_search(company: str) -> list[str]:
    """
    Use web search to find the company's official website.
    Filters out social/aggregator sites and returns a ranked list of
    plausible base URLs. Safe: returns [] if search is unavailable.
    """
    try:
        from ai_engine.agents.tools import _web_search  # local import avoids circular
    except Exception:
        return []

    queries = [
        f'"{company}" official website',
        f"{company} company site",
        f"{company} about us",
    ]
    seen: set[str] = set()
    ranked: list[str] = []
    for q in queries:
        try:
            res = await _web_search(q, max_results=5)
        except Exception:
            continue
        for item in (res.get("results") or []):
            link = (item.get("link") or "").strip()
            if not link.startswith("http"):
                continue
            domain = _domain_of(link)
            if not domain or domain in _DOMAIN_BLOCKLIST:
                continue
            # Skip any subdomain of a blocklisted aggregator
            if any(domain.endswith("." + blocked) for blocked in _DOMAIN_BLOCKLIST):
                continue
            base = f"https://{domain}"
            if base in seen:
                continue
            seen.add(base)
            ranked.append(base)
        if len(ranked) >= 4:
            break
    return ranked[:4]


# Priority keywords in URL paths — if a sitemap lists these, they're worth
# crawling. Ordered by information density for career intel.
_SITEMAP_PRIORITY_KEYWORDS = [
    "about", "company", "team", "leadership", "people", "careers",
    "mission", "values", "culture", "engineering", "blog", "news",
    "press", "investors", "products", "solutions", "customers",
    "case-studies", "pricing", "security", "contact",
]
# Path fragments we never want to crawl even if they appear in a sitemap.
_SITEMAP_PATH_BLOCK = (
    "/legal", "/privacy", "/terms", "/cookie", "/policy",
    "/gdpr", "/ccpa", "/login", "/signin", "/signup", "/register",
    "/cart", "/checkout", "/account", "/404", "/500",
    ".pdf", ".zip", ".xml", ".json", ".rss",
)


async def _fetch_sitemap_urls(base_url: str, max_urls: int = 20) -> list[str]:
    """
    Discover crawl targets by asking the site itself.

    Tries robots.txt first (authoritative pointer to sitemap), then
    falls back to /sitemap.xml and /sitemap_index.xml. Handles sitemap
    index files (one level of nesting) and filters out noise paths.
    Returns up to max_urls same-origin URLs ranked by priority keywords.
    """
    base = base_url.rstrip("/")
    base_domain = _domain_of(base)
    if not base_domain:
        return []

    sitemap_urls: list[str] = []

    # 1. robots.txt → Sitemap: <url>
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(
                f"{base}/robots.txt",
                headers={"User-Agent": _USER_AGENT, "Accept": "text/plain"},
            )
            if resp.status_code == 200:
                for line in resp.text.splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        sitemap_urls.append(line.split(":", 1)[1].strip())
    except Exception:
        pass

    # 2. Conventional locations
    for path in ("/sitemap.xml", "/sitemap_index.xml", "/sitemap-index.xml"):
        candidate = f"{base}{path}"
        if candidate not in sitemap_urls:
            sitemap_urls.append(candidate)

    # 3. Fetch each sitemap (one level of index expansion allowed)
    collected: list[str] = []
    seen_sitemaps: set[str] = set()

    async def _read_sitemap(sm_url: str, depth: int = 0) -> None:
        if sm_url in seen_sitemaps or depth > 1:
            return
        seen_sitemaps.add(sm_url)
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
                resp = await client.get(
                    sm_url,
                    headers={"User-Agent": _USER_AGENT, "Accept": "application/xml, text/xml"},
                )
                if resp.status_code != 200 or not resp.text:
                    return
                xml = resp.text
        except Exception:
            return

        # <sitemap><loc>…</loc></sitemap> → index; recurse once
        nested = re.findall(r"<sitemap>\s*<loc>\s*([^<\s]+)\s*</loc>", xml, re.IGNORECASE)
        if nested and depth == 0:
            for n in nested[:3]:
                await _read_sitemap(n.strip(), depth=1)
            return

        # <url><loc>…</loc></url> → leaf URLs
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml, re.IGNORECASE)
        for loc in locs:
            loc = loc.strip()
            if not loc.startswith("http"):
                continue
            if _domain_of(loc) != base_domain:
                continue
            low = loc.lower()
            if any(b in low for b in _SITEMAP_PATH_BLOCK):
                continue
            collected.append(loc)

    for sm in sitemap_urls[:4]:
        await _read_sitemap(sm)
        if len(collected) >= 200:
            break

    if not collected:
        return []

    def _rank(url: str) -> tuple[int, int]:
        low = url.lower()
        for idx, kw in enumerate(_SITEMAP_PRIORITY_KEYWORDS):
            if kw in low:
                return (idx, len(url))
        return (len(_SITEMAP_PRIORITY_KEYWORDS), len(url))

    seen: set[str] = set()
    unique: list[str] = []
    for u in collected:
        if u in seen:
            continue
        seen.add(u)
        unique.append(u)

    unique.sort(key=_rank)
    return unique[:max_urls]


def _extract_text(html: str) -> dict[str, str]:
    """
    Extract title, description, headings, body text, and social links from HTML.

    Prefers selectolax (fast C parser, proper DOM) when available. Falls back
    to the legacy regex-based extractor if selectolax is unavailable or the
    document parse fails for any reason.
    """
    # --- Try selectolax first ---
    try:
        from selectolax.parser import HTMLParser  # type: ignore
        tree = HTMLParser(html)

        # Remove noise nodes
        for selector in ("script", "style", "noscript", "template", "svg"):
            for node in tree.css(selector):
                node.decompose()

        # Title
        title_node = tree.css_first("title")
        title = (title_node.text() if title_node else "").strip()

        # Meta description (description or og:description, in either attr order)
        description = ""
        for sel in (
            'meta[name="description"]',
            'meta[property="og:description"]',
            'meta[name="twitter:description"]',
        ):
            node = tree.css_first(sel)
            if node:
                val = (node.attributes.get("content") or "").strip()
                if val:
                    description = val
                    break

        # Headings (H1/H2/H3), capped
        headings: list[str] = []
        for h in tree.css("h1, h2, h3"):
            txt = h.text(strip=True) if hasattr(h, "text") else ""
            if txt and len(txt) < 200:
                headings.append(txt)
            if len(headings) >= 20:
                break

        # Links + social categorisation
        social: dict[str, str] = {}
        for a in tree.css("a[href]"):
            href = (a.attributes.get("href") or "").strip()
            if not href or href.startswith(("#", "javascript:", "mailto:")):
                continue
            low = href.lower()
            if "linkedin.com" in low and "linkedin" not in social:
                social["linkedin"] = href
            elif ("twitter.com" in low or "x.com" in low) and "twitter" not in social:
                social["twitter"] = href
            elif "github.com" in low and "github" not in social:
                social["github"] = href
            elif "glassdoor.com" in low and "glassdoor" not in social:
                social["glassdoor"] = href
            elif "youtube.com" in low and "youtube" not in social:
                social["youtube"] = href
            elif "instagram.com" in low and "instagram" not in social:
                social["instagram"] = href

        # Main body text — prefer <main> / <article> / role=main, else <body>
        main_node = (
            tree.css_first("main")
            or tree.css_first("article")
            or tree.css_first('[role="main"]')
            or tree.css_first("body")
            or tree.root
        )
        body = main_node.text(separator=" ", strip=True) if main_node else ""
        # Collapse whitespace
        body = re.sub(r"\s+", " ", body).strip()

        return {
            "title": title,
            "description": description,
            "headings": "; ".join(headings[:15]),
            "body": body[:8000],
            "social_links": str(social) if social else "",
        }
    except Exception:
        pass

    # --- Regex fallback (kept intentionally; handles broken HTML selectolax
    #     sometimes refuses to parse) ---
    cleaned = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<style[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"<!--.*?-->", "", cleaned, flags=re.DOTALL)

    title_m = re.search(r"<title[^>]*>(.*?)</title>", cleaned, re.IGNORECASE | re.DOTALL)
    title = title_m.group(1).strip() if title_m else ""

    desc_m = re.search(
        r'<meta\s+(?:name|property)=["\'](?:description|og:description)["\']\s+content=["\']([^"\']*)["\']',
        cleaned, re.IGNORECASE,
    )
    if not desc_m:
        desc_m = re.search(
            r'<meta\s+content=["\']([^"\']*)["\']\s+(?:name|property)=["\'](?:description|og:description)["\']',
            cleaned, re.IGNORECASE,
        )
    description = desc_m.group(1).strip() if desc_m else ""

    headings = re.findall(r"<h[1-3][^>]*>(.*?)</h[1-3]>", cleaned, re.IGNORECASE | re.DOTALL)
    headings = [re.sub(r"<[^>]+>", "", h).strip() for h in headings[:20]]

    links = re.findall(r'href=["\']([^"\']*)["\']', cleaned, re.IGNORECASE)
    body = re.sub(r"<[^>]+>", " ", cleaned)
    body = re.sub(r"\s+", " ", body).strip()

    social: dict[str, str] = {}
    for link in links:
        link_lower = link.lower()
        if "linkedin.com" in link_lower:
            social.setdefault("linkedin", link)
        elif "twitter.com" in link_lower or "x.com" in link_lower:
            social.setdefault("twitter", link)
        elif "github.com" in link_lower:
            social.setdefault("github", link)
        elif "glassdoor.com" in link_lower:
            social.setdefault("glassdoor", link)

    return {
        "title": title,
        "description": description,
        "headings": "; ".join(headings[:15]),
        "body": body[:8000],
        "social_links": str(social) if social else "",
    }


class WebsiteIntelAgent(SubAgent):
    """Deep website crawl — fetches multiple pages in parallel for maximum intel."""

    def __init__(self, ai_client: Optional[AIClient] = None):
        super().__init__(name="website_intel", ai_client=ai_client)

    async def run(self, context: dict) -> SubAgentResult:
        company = context.get("company", "") or context.get("company_name", "")
        company_url = context.get("company_url")
        on_event = context.get("on_event")

        if not company:
            return SubAgentResult(agent_name=self.name, error="No company name")

        # URL discovery: explicit URL → web search → TLD guessing.
        base_urls: list[str] = []
        if company_url:
            base_urls.append(company_url.rstrip("/"))

        if not base_urls:
            if on_event:
                await _emit(on_event, f"Searching for official site of {company}…", "running", "website")
            search_hits = await _discover_url_via_search(company)
            if search_hits:
                base_urls.extend(search_hits)
                if on_event:
                    await _emit(
                        on_event,
                        f"Search found {len(search_hits)} candidate site(s).",
                        "running", "website",
                        metadata={"candidates": search_hits},
                    )

        # Append TLD-guessed URLs last so they only get tried if search failed
        for g in _guess_urls(company, None):
            if g not in base_urls:
                base_urls.append(g)

        if not base_urls:
            return SubAgentResult(agent_name=self.name, error="Cannot determine company URL")

        # Find a working base URL first
        working_base = None
        for base in base_urls:
            if on_event:
                await _emit(on_event, f"Probing {base}…", "running", "website", url=base)
            content = await _fetch(base)
            if content:
                working_base = base
                break

        if not working_base:
            if on_event:
                await _emit(on_event, "No reachable company website found.", "warning", "website")
            return SubAgentResult(
                agent_name=self.name,
                data={"status": "no_website_found", "urls_tried": base_urls[:4]},
                confidence=0.1,
            )

        if on_event:
            await _emit(on_event, f"Website found at {working_base}. Crawling pages…", "running", "website", url=working_base)

        # Sitemap-first crawl: ask the site what its pages are. If a sitemap
        # exists, those URLs beat the hardcoded guess list for both coverage
        # (finds /handbook, /engineering-blog, /customers/xyz, etc.) and
        # efficiency (no wasted requests on nonexistent paths).
        pages_to_fetch: dict[str, str] = {}
        sitemap_urls = await _fetch_sitemap_urls(working_base, max_urls=20)
        if sitemap_urls:
            if on_event:
                await _emit(
                    on_event,
                    f"Sitemap found: {len(sitemap_urls)} ranked URL(s). Crawling.",
                    "running", "website",
                    url=working_base,
                    metadata={"sitemap_count": len(sitemap_urls)},
                )
            # Always keep the homepage
            pages_to_fetch["homepage"] = working_base
            # Name each sitemap URL by its last meaningful path segment
            for url in sitemap_urls:
                try:
                    import urllib.parse as up
                    path = up.urlparse(url).path.rstrip("/")
                    segments = [s for s in path.split("/") if s]
                    name = segments[-1] if segments else "page"
                    # Limit to alphanumeric/underscore for cleanliness
                    name = re.sub(r"[^a-z0-9_-]", "_", name.lower())[:40] or "page"
                except Exception:
                    name = "page"
                # De-dupe names
                key = name
                counter = 2
                while key in pages_to_fetch:
                    key = f"{name}_{counter}"
                    counter += 1
                pages_to_fetch[key] = url
        else:
            if on_event:
                await _emit(
                    on_event,
                    "No sitemap — crawling common paths.",
                    "running", "website",
                    url=working_base,
                )
            pages_to_fetch = {name: f"{working_base}{path}" for name, path in _PAGE_PATHS}

        fetch_tasks = {name: _fetch(url) for name, url in pages_to_fetch.items()}
        results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)

        page_data: dict[str, dict] = {}
        pages_found = 0
        for (name, _), result in zip(fetch_tasks.items(), results):
            if isinstance(result, Exception) or not result:
                continue
            extracted = _extract_text(result)
            if extracted["body"] and len(extracted["body"]) > 50:
                page_data[name] = extracted
                pages_found += 1

        if on_event:
            await _emit(
                on_event,
                f"Crawled {pages_found} pages from {working_base}.",
                "completed", "website",
                url=working_base,
                metadata={"pages_found": pages_found, "pages": list(page_data.keys())},
            )

        # Build evidence items from extracted data
        evidence_items: list[dict] = []
        for page_name, data in page_data.items():
            if data.get("description"):
                evidence_items.append({
                    "fact": f"[{page_name}] {data['description'][:300]}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                })
            if data.get("headings"):
                evidence_items.append({
                    "fact": f"[{page_name}] Headings: {data['headings'][:300]}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                })

        # Compile raw text for downstream synthesis
        full_text_parts = []
        for page_name, data in page_data.items():
            full_text_parts.append(f"=== {page_name.upper()} PAGE ===")
            if data.get("title"):
                full_text_parts.append(f"Title: {data['title']}")
            if data.get("description"):
                full_text_parts.append(f"Description: {data['description']}")
            full_text_parts.append(data.get("body", "")[:4000])
            full_text_parts.append("")

        confidence = min(0.95, 0.3 + pages_found * 0.1)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "base_url": working_base,
                "pages_found": pages_found,
                "page_names": list(page_data.keys()),
                "page_data": {k: {kk: vv[:500] for kk, vv in v.items()} for k, v in page_data.items()},
                "full_text": "\n".join(full_text_parts)[:16000],
                "social_links": page_data.get("homepage", {}).get("social_links", ""),
            },
            evidence_items=evidence_items,
            confidence=confidence,
        )


async def _fetch(url: str) -> str:
    """Fetch a page with proper error handling."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": _USER_AGENT, "Accept": "text/html"})
            if resp.status_code != 200:
                return ""
            return resp.text[:30000]
    except Exception:
        return ""


async def _emit(callback, message: str, status: str, source: str, url: str | None = None, metadata: dict | None = None):
    """Emit event to the pipeline callback."""
    payload: dict[str, Any] = {"stage": "recon", "status": status, "message": message, "source": source}
    if url:
        payload["url"] = url
    if metadata:
        payload["metadata"] = metadata
    try:
        maybe = callback(payload)
        if asyncio.iscoroutine(maybe):
            await maybe
    except Exception:
        pass
