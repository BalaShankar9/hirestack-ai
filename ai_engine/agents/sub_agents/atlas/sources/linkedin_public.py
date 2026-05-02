"""ATLAS v2 — LinkedIn public provider (HTML-only, no API key).

LinkedIn aggressively gates its public profile pages: most unauthenticated
requests return HTTP 999 (rate-limit / bot-block) or a login wall. This
provider does ONE best-effort GET and returns ``success=False`` whenever
the response is missing, blocked, or unparseable. The fusion layer treats
absence as "no signal", never as a hard failure.

Default OFF — opt-in via env flag at the orchestrator wiring slice. This
file is pure provider logic.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Optional

from ai_engine.agents.sub_agents.recon_swarm.schemas import ProviderResult

logger = logging.getLogger(__name__)


_LI_PROFILE_URL = "https://www.linkedin.com/in/{slug}"

# Rotating UA — modern desktop Chrome strings. LinkedIn fingerprints
# hard so this is necessary-but-not-sufficient; we still expect 999.
_USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

# OpenGraph / meta extraction regexes (cheap; no bs4 dep).
_META_RE = re.compile(
    r'<meta[^>]+(?:property|name)=["\'](?P<key>[^"\']+)["\'][^>]+content=["\'](?P<val>[^"\']*)["\']',
    re.IGNORECASE,
)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# Login-wall / block markers we treat as "no data".
_BLOCK_MARKERS = (
    "authwall",
    "sign in to linkedin",
    "sign-in-modal",
    "join linkedin",
    "/uas/login",
)


class LinkedInPublicProvider:
    """Best-effort public LinkedIn profile scraper. Defaults to no signal."""

    name = "linkedin_public"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        timeout_s: float = 6.0,
        ua_index: int = 0,
    ) -> None:
        self._client = http_client
        self._timeout_s = timeout_s
        self._ua = _USER_AGENTS[ua_index % len(_USER_AGENTS)]

    async def fetch(self, *, profile_slug: str, **_: Any) -> ProviderResult:
        s = time.perf_counter()
        slug = self._normalize_slug(profile_slug)
        if not slug:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty profile slug",
            )
        client, owned = await self._get_client()
        try:
            resp = await client.get(_LI_PROFILE_URL.format(slug=slug))
            status = getattr(resp, "status_code", 0)
            # 999 is LinkedIn's "blocked" code; 403 / 401 are also seen.
            if status != 200:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error=f"status={status}",
                )
            html = getattr(resp, "text", "") or ""
            if not html or self._is_blocked(html):
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error="login wall / authwall",
                )
            payload = self._extract(html, slug)
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw=payload,
            )
        except Exception as exc:  # noqa: BLE001
            logger.info("linkedin_public fetch failed slug=%s exc=%s", slug, exc)
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
    def _normalize_slug(raw: str) -> Optional[str]:
        s = (raw or "").strip()
        if not s:
            return None
        if "linkedin.com/in/" in s:
            s = s.split("linkedin.com/in/", 1)[1]
        s = s.strip("/").split("/", 1)[0].split("?", 1)[0]
        # LinkedIn slugs allow letters, digits, hyphens, underscores.
        cleaned = "".join(c for c in s if c.isalnum() or c in "-_")
        return cleaned.lower() or None

    @staticmethod
    def _is_blocked(html: str) -> bool:
        lower = html.lower()
        return any(marker in lower for marker in _BLOCK_MARKERS)

    @staticmethod
    def _extract(html: str, slug: str) -> Dict[str, Any]:
        meta: Dict[str, str] = {}
        for m in _META_RE.finditer(html):
            key = m.group("key").strip().lower()
            val = m.group("val").strip()
            # First wins (LinkedIn pages occasionally repeat keys).
            meta.setdefault(key, val)

        title_match = _TITLE_RE.search(html)
        title = (title_match.group(1).strip() if title_match else "")[:300]

        # OpenGraph: og:title is "<Name> - <Headline> | LinkedIn".
        og_title = meta.get("og:title", "") or title
        name, headline = _split_og_title(og_title)

        return {
            "slug": slug,
            "name": name,
            "headline": headline,
            "description": meta.get("og:description", "")[:500],
            "image_url": meta.get("og:image", ""),
            "profile_url": meta.get("og:url", "") or _LI_PROFILE_URL.format(slug=slug),
            "raw_title": title,
        }

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        return httpx.AsyncClient(timeout=self._timeout_s, headers=headers, follow_redirects=True), True


def _split_og_title(og_title: str) -> tuple[str, str]:
    """Split LinkedIn's standard og:title into (name, headline).

    Format observed in the wild:
        "Ada Lovelace - Staff Engineer at Acme | LinkedIn"
    Fallbacks: strip trailing " | LinkedIn"; if no " - " separator,
    return (full_title, "").
    """
    s = og_title.strip()
    if s.endswith("| LinkedIn"):
        s = s[: -len("| LinkedIn")].strip()
    elif s.endswith("LinkedIn"):
        s = s[: -len("LinkedIn")].rstrip(" |-")
    if " - " in s:
        name, _, headline = s.partition(" - ")
        return name.strip(), headline.strip()
    return s, ""
