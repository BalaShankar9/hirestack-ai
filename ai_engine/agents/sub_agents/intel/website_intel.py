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


# ── Page type classifier + specialist extractors ──────────────────────

def _classify_page(url: str, name: str) -> str:
    """
    Classify a page URL into a handler category.

    Returns one of: 'careers', 'press', 'blog', 'investors', 'generic'.
    Classification is by URL path + the page `name` key we generated, so
    it works for both sitemap URLs (with real paths) and the hardcoded
    _PAGE_PATHS names.
    """
    low = (url + " " + name).lower()
    # Order matters — investors before press because many press releases
    # mention "investors", and careers before blog (careers can be under
    # /blog/careers in some sites).
    if any(kw in low for kw in ("/careers", "/jobs", "/join", "/work-with-us", "/hiring")):
        return "careers"
    if "careers" in name or "jobs" in name or "hiring" in name:
        return "careers"
    if any(kw in low for kw in ("/investors", "/investor-relations", "/ir/")):
        return "investors"
    if "investor" in name:
        return "investors"
    if any(kw in low for kw in ("/press", "/news", "/announcements", "/newsroom")):
        return "press"
    if "press" in name or "news" in name or "announcement" in name:
        return "press"
    if any(kw in low for kw in ("/blog", "/posts", "/articles", "/engineering")):
        return "blog"
    if "blog" in name or "engineering" in name:
        return "blog"
    return "generic"


# ISO date or common human date patterns. Captures the date string.
_DATE_PATTERNS = [
    # ISO 8601 (covers most meta tags: 2026-02-14T09:30:00+00:00, 2026-02-14)
    re.compile(r"\b(20[12]\d-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:?\d{2})?)?)\b"),
    # "Feb 14, 2026" / "February 14, 2026"
    re.compile(
        r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+20[12]\d)\b",
        re.IGNORECASE,
    ),
    # "14 Feb 2026"
    re.compile(
        r"\b(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+20[12]\d)\b",
        re.IGNORECASE,
    ),
]


def _extract_page_date(html: str) -> Optional[str]:
    """
    Pull the publication date from common meta tags first, then fall back
    to visible text patterns. Returns an ISO-ish string when possible
    (leaves human-readable strings intact otherwise), or None.

    Priority:
      1. <meta property="article:published_time">
      2. <meta property="og:updated_time">
      3. <time datetime="…">
      4. First date-like substring in the visible text.
    """
    # Meta tags (case-insensitive attr match)
    meta_patterns = [
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']article:published_time["\']',
        r'<meta[^>]+property=["\']og:updated_time["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+name=["\']date["\'][^>]+content=["\']([^"\']+)["\']',
    ]
    for pat in meta_patterns:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # <time datetime="…">
    m = re.search(r"<time[^>]+datetime=[\"']([^\"']+)[\"']", html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # JSON-LD datePublished / dateModified
    m = re.search(r'"(?:datePublished|dateModified)"\s*:\s*"([^"]+)"', html, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Fall back to visible-text date
    # Strip tags cheaply for this pass
    text = re.sub(r"<[^>]+>", " ", html)
    for pat in _DATE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def _days_since(date_str: str) -> Optional[int]:
    """Parse a date string we extracted and return days since today, or None."""
    if not date_str:
        return None
    try:
        from datetime import datetime, timezone
        s = date_str.strip()
        # Try common formats
        for fmt in (
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ):
            try:
                dt = datetime.strptime(s.replace("Z", "+0000"), fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                return max(0, (now - dt).days)
            except Exception:
                continue
        # ISO with fractional seconds
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return max(0, (now - dt).days)
        except Exception:
            pass
    except Exception:
        pass
    return None


# Common tech-stack keywords we look for on engineering blogs / careers pages.
_TECH_KEYWORDS = [
    "python", "java", "kotlin", "scala", "ruby", "rust", "go", "golang",
    "javascript", "typescript", "node.js", "nodejs", "deno", "bun",
    "react", "next.js", "vue", "angular", "svelte", "remix",
    "django", "flask", "fastapi", "rails", "spring boot", "express",
    "postgres", "postgresql", "mysql", "mongodb", "redis", "cassandra",
    "elasticsearch", "opensearch", "clickhouse", "snowflake", "databricks",
    "kafka", "rabbitmq", "pubsub", "sqs", "sns",
    "kubernetes", "k8s", "docker", "terraform", "pulumi", "ansible",
    "aws", "gcp", "azure", "cloudflare", "vercel", "netlify", "heroku",
    "graphql", "grpc", "rest", "websocket", "webrtc",
    "tensorflow", "pytorch", "huggingface", "langchain", "openai", "anthropic",
    "pandas", "numpy", "spark", "airflow", "dagster", "dbt",
    "ci/cd", "github actions", "gitlab ci", "circleci", "jenkins",
    "datadog", "sentry", "new relic", "prometheus", "grafana",
]


def _extract_tech_stack(body: str) -> list[str]:
    """Return distinct tech keywords mentioned in the body text (lowercased)."""
    if not body:
        return []
    low = body.lower()
    found: list[str] = []
    seen: set[str] = set()
    for kw in _TECH_KEYWORDS:
        if kw in low and kw not in seen:
            seen.add(kw)
            found.append(kw)
    return found[:25]


# Role / job-title cues on careers pages.
_ROLE_KEYWORDS = [
    "engineer", "developer", "architect", "manager", "director",
    "designer", "analyst", "scientist", "researcher", "lead",
    "staff", "principal", "senior", "junior", "intern",
    "product", "program", "project", "marketing", "sales",
    "customer success", "recruiter", "operations", "finance",
]


def _extract_careers_signals(body: str, headings: str) -> dict[str, Any]:
    """Pull careers-specific signals: role count, categories, ATS hint."""
    signals: dict[str, Any] = {}
    if not body:
        return signals
    combined = (body + " " + headings).lower()

    # Naive role count — headings that look like job titles
    role_hits: list[str] = []
    for line in headings.split(";"):
        line = line.strip().lower()
        if 3 <= len(line) <= 80 and any(k in line for k in _ROLE_KEYWORDS):
            role_hits.append(line)
    signals["heading_role_mentions"] = len(role_hits)
    if role_hits:
        signals["sample_roles"] = role_hits[:8]

    # ATS fingerprints
    ats_fingerprints = {
        "greenhouse": ["boards.greenhouse.io", "greenhouse.io/", "gh_jid=", "greenhouse"],
        "lever": ["jobs.lever.co", "lever.co/", "lever-job"],
        "workday": ["myworkdayjobs.com", "workday.com/"],
        "ashby": ["jobs.ashbyhq.com", "ashbyhq.com/"],
        "smartrecruiters": ["smartrecruiters.com/"],
        "bamboohr": ["bamboohr.com/jobs", "bamboohr"],
        "jobvite": ["jobvite.com/"],
        "icims": ["icims.com/"],
        "successfactors": ["successfactors.com", "successfactors.eu"],
        "recruitee": ["recruitee.com/"],
        "teamtailor": ["teamtailor.com/"],
    }
    detected_ats: list[str] = []
    for ats, fps in ats_fingerprints.items():
        if any(fp in combined for fp in fps):
            detected_ats.append(ats)
    if detected_ats:
        signals["ats_detected"] = detected_ats

    return signals


def _extract_press_signals(body: str, html_sample: str) -> dict[str, Any]:
    """Press / newsroom signals: latest headline + whether the page is fresh."""
    signals: dict[str, Any] = {}
    if not body:
        return signals
    # Try to find a dated headline near the top of the body
    lines = [ln.strip() for ln in body.split(". ") if ln.strip()]
    # Grab first 3 substantive lines as candidate recent headlines
    signals["recent_headlines"] = [ln[:200] for ln in lines[:3]]
    # Extract dates visible in the body
    dates_found: list[str] = []
    for pat in _DATE_PATTERNS:
        dates_found.extend(pat.findall(body))
        if len(dates_found) >= 5:
            break
    if dates_found:
        signals["dates_in_body"] = dates_found[:5]
    return signals


def _extract_investors_signals(body: str) -> dict[str, Any]:
    """Investor-relations page signals: funding rounds, investor names."""
    signals: dict[str, Any] = {}
    if not body:
        return signals
    low = body.lower()
    # Funding round mentions
    round_patterns = [
        r"\b(series\s+[a-z])\b",
        r"\b(seed|pre-seed|pre\s+seed|bridge|growth|ipo)\s+(?:round|funding|financing)\b",
        r"\$(\d+(?:\.\d+)?)\s*(?:m|million|b|billion)\b",
    ]
    hits: list[str] = []
    for p in round_patterns:
        for m in re.finditer(p, low):
            hits.append(m.group(0))
            if len(hits) >= 8:
                break
    if hits:
        signals["funding_mentions"] = hits[:8]
    return signals


def _extract_blog_signals(body: str) -> dict[str, Any]:
    """Engineering-blog / blog signals: post cadence hints, tech stack."""
    signals: dict[str, Any] = {}
    if not body:
        return signals
    tech = _extract_tech_stack(body)
    if tech:
        signals["tech_keywords"] = tech
    # Count visible dates as a cadence proxy
    seen: set[str] = set()
    for pat in _DATE_PATTERNS:
        for m in pat.findall(body):
            seen.add(m if isinstance(m, str) else str(m))
            if len(seen) >= 15:
                break
    signals["dated_entries_count"] = len(seen)
    return signals


def _run_specialist(page_type: str, html: str, extracted: dict[str, str]) -> dict[str, Any]:
    """Dispatch a page to its specialist extractor. Always returns a dict."""
    body = extracted.get("body", "") or ""
    headings = extracted.get("headings", "") or ""
    specialist: dict[str, Any] = {"page_type": page_type}
    try:
        if page_type == "careers":
            specialist.update(_extract_careers_signals(body, headings))
        elif page_type == "press":
            specialist.update(_extract_press_signals(body, html))
        elif page_type == "investors":
            specialist.update(_extract_investors_signals(body))
        elif page_type == "blog":
            specialist.update(_extract_blog_signals(body))
    except Exception:
        pass
    # Freshness applies to every page type — we always care when the site
    # was last updated.
    date_str = _extract_page_date(html)
    if date_str:
        specialist["published_at"] = date_str
        days = _days_since(date_str)
        if days is not None:
            specialist["days_since_published"] = days
    return specialist


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
        specialist_data: dict[str, dict[str, Any]] = {}
        pages_found = 0
        for (name, url), result in zip(pages_to_fetch.items(), results):
            if isinstance(result, Exception) or not result:
                continue
            extracted = _extract_text(result)
            if not (extracted["body"] and len(extracted["body"]) > 50):
                continue
            page_data[name] = extracted
            pages_found += 1
            # Run the specialist for this page type using the raw HTML
            # (needed for <time>/<meta> date extraction) + the already
            # cleaned body text.
            try:
                p_type = _classify_page(url, name)
                specialist_data[name] = _run_specialist(p_type, result, extracted)
            except Exception:
                specialist_data[name] = {"page_type": "generic"}

        # Site-level freshness = minimum days_since_published across pages.
        # If no dated pages found, leave as None rather than lying.
        fresh_days: list[int] = []
        for sp in specialist_data.values():
            d = sp.get("days_since_published")
            if isinstance(d, int):
                fresh_days.append(d)
        site_freshness_days = min(fresh_days) if fresh_days else None

        # Aggregate signals across all specialist pages
        aggregated_tech: list[str] = []
        seen_tech: set[str] = set()
        detected_ats: list[str] = []
        role_signal_total = 0
        funding_mentions: list[str] = []
        page_types_found: dict[str, int] = {}
        for sp in specialist_data.values():
            pt = sp.get("page_type", "generic")
            page_types_found[pt] = page_types_found.get(pt, 0) + 1
            for t in (sp.get("tech_keywords") or []):
                if t not in seen_tech:
                    seen_tech.add(t)
                    aggregated_tech.append(t)
            for ats in (sp.get("ats_detected") or []):
                if ats not in detected_ats:
                    detected_ats.append(ats)
            role_signal_total += sp.get("heading_role_mentions") or 0
            funding_mentions.extend(sp.get("funding_mentions") or [])

        if on_event:
            await _emit(
                on_event,
                f"Crawled {pages_found} pages from {working_base}.",
                "completed", "website",
                url=working_base,
                metadata={
                    "pages_found": pages_found,
                    "pages": list(page_data.keys()),
                    "page_types": page_types_found,
                    "site_freshness_days": site_freshness_days,
                    "ats_detected": detected_ats or None,
                    "tech_keywords": aggregated_tech[:12] or None,
                },
            )

        # Build evidence items from extracted data — baseline + specialist
        evidence_items: list[dict] = []
        for page_name, data in page_data.items():
            sp = specialist_data.get(page_name, {})
            p_type = sp.get("page_type", "generic")

            if data.get("description"):
                evidence_items.append({
                    "fact": f"[{page_name}] {data['description'][:300]}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                    "page_type": p_type,
                })
            if data.get("headings"):
                evidence_items.append({
                    "fact": f"[{page_name}] Headings: {data['headings'][:300]}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                    "page_type": p_type,
                })

            # Freshness evidence — only when we found a real date
            if sp.get("published_at"):
                days = sp.get("days_since_published")
                age_str = f" ({days}d ago)" if isinstance(days, int) else ""
                evidence_items.append({
                    "fact": f"[{page_name}] Published {sp['published_at']}{age_str}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                    "page_type": p_type,
                    "published_at": sp.get("published_at"),
                    "days_since_published": days,
                })

            # Specialist evidence per page type
            if p_type == "careers":
                if sp.get("ats_detected"):
                    evidence_items.append({
                        "fact": f"Careers page uses ATS: {', '.join(sp['ats_detected'])}",
                        "source": f"website:{page_name}",
                        "tier": "DERIVED",
                        "sub_agent": self.name,
                        "page_type": "careers",
                    })
                if sp.get("sample_roles"):
                    evidence_items.append({
                        "fact": f"Careers page role mentions: {', '.join(sp['sample_roles'][:5])}",
                        "source": f"website:{page_name}",
                        "tier": "VERBATIM",
                        "sub_agent": self.name,
                        "page_type": "careers",
                    })
            elif p_type == "investors" and sp.get("funding_mentions"):
                evidence_items.append({
                    "fact": f"Investor page references: {', '.join(sp['funding_mentions'][:5])}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                    "page_type": "investors",
                })
            elif p_type == "press" and sp.get("recent_headlines"):
                evidence_items.append({
                    "fact": f"Press headlines: {' | '.join(sp['recent_headlines'][:2])[:400]}",
                    "source": f"website:{page_name}",
                    "tier": "VERBATIM",
                    "sub_agent": self.name,
                    "page_type": "press",
                })
            elif p_type == "blog" and sp.get("tech_keywords"):
                evidence_items.append({
                    "fact": f"Blog tech keywords: {', '.join(sp['tech_keywords'][:10])}",
                    "source": f"website:{page_name}",
                    "tier": "DERIVED",
                    "sub_agent": self.name,
                    "page_type": "blog",
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

        # Confidence: base + bonus per page, plus a small boost when we
        # have freshness signal (dated pages prove the site isn't abandoned).
        confidence = 0.3 + pages_found * 0.05
        if site_freshness_days is not None and site_freshness_days <= 180:
            confidence += 0.05
        if detected_ats:
            confidence += 0.05
        confidence = min(0.95, confidence)

        return SubAgentResult(
            agent_name=self.name,
            data={
                "base_url": working_base,
                "pages_found": pages_found,
                "page_names": list(page_data.keys()),
                "page_data": {k: {kk: vv[:500] for kk, vv in v.items()} for k, v in page_data.items()},
                "full_text": "\n".join(full_text_parts)[:16000],
                "social_links": page_data.get("homepage", {}).get("social_links", ""),
                # Tier 4 additions:
                "specialist_data": specialist_data,
                "site_freshness_days": site_freshness_days,
                "page_types_found": page_types_found,
                "tech_keywords": aggregated_tech,
                "ats_detected": detected_ats,
                "careers_role_mentions": role_signal_total,
                "funding_mentions": funding_mentions[:10],
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
