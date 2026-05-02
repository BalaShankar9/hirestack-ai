"""ATLAS v2 — levels.fyi public-page salary scraper (HTML-only, no API key).

levels.fyi exposes per-company salary breakdowns at::

    https://www.levels.fyi/companies/{company_slug}/salaries/{role_slug}

The page is a Next.js / SSR-hydrated React app: enough information leaks
into ``<script id="__NEXT_DATA__">…</script>`` to extract realistic
percentile salary bands without a headless browser. We parse the JSON
blob, walk a small set of candidate paths to find the percentile array,
and surface ``{p25, p50, p75}`` (USD).

Default OFF — opt-in via ``RECON_LEVELS_PROVIDER=real`` (orchestrator
slice). When unset / blocked / parse-fails, we return ``success=False``;
the archetype layer treats absence as an empty ``salary_band``.
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from ai_engine.agents.sub_agents.recon_swarm.schemas import ProviderResult

logger = logging.getLogger(__name__)


_LEVELS_URL = "https://www.levels.fyi/companies/{company}/salaries/{role}"

_USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
)

_NEXT_DATA_RE = re.compile(
    r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(?P<blob>.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

_BLOCK_MARKERS = (
    "captcha",
    "access denied",
    "cloudflare",
    "are you a human",
)

# Where to look inside the parsed __NEXT_DATA__ blob for percentile data.
# Schema drift on levels.fyi is the norm; we walk multiple candidate keys
# and bail out cleanly if none match.
_PERCENTILE_KEYS = ("percentiles", "salaryPercentiles", "compensation")
_P25_KEYS = ("p25", "twentyFifthPercentile", "percentile25", "25th")
_P50_KEYS = ("p50", "median", "fiftiethPercentile", "percentile50", "50th")
_P75_KEYS = ("p75", "seventyFifthPercentile", "percentile75", "75th")


class LevelsFYIProvider:
    """Best-effort levels.fyi salary scraper. Defaults to no signal."""

    name = "levels_fyi"
    layer = 1

    def __init__(
        self,
        *,
        http_client: Optional[Any] = None,
        timeout_s: float = 8.0,
        ua_index: int = 0,
    ) -> None:
        self._client = http_client
        self._timeout_s = timeout_s
        self._ua = _USER_AGENTS[ua_index % len(_USER_AGENTS)]

    async def fetch(
        self,
        *,
        company: str,
        role: str = "software-engineer",
        **_: Any,
    ) -> ProviderResult:
        s = time.perf_counter()
        company_slug = self._normalize_slug(company)
        role_slug = self._normalize_slug(role) or "software-engineer"
        if not company_slug:
            return ProviderResult(
                provider=self.name, layer=self.layer, success=False,
                latency_ms=int((time.perf_counter() - s) * 1000),
                error="empty company",
            )
        url = _LEVELS_URL.format(company=company_slug, role=role_slug)
        client, owned = await self._get_client()
        try:
            resp = await client.get(url)
            status = getattr(resp, "status_code", 0)
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
                    error="blocked / captcha",
                )
            band = self._extract_band(html)
            if not band:
                return ProviderResult(
                    provider=self.name, layer=self.layer, success=False,
                    latency_ms=int((time.perf_counter() - s) * 1000),
                    error="no percentile data found",
                )
            return ProviderResult(
                provider=self.name, layer=self.layer, success=True,
                latency_ms=int((time.perf_counter() - s) * 1000),
                raw={
                    "company": company_slug,
                    "role": role_slug,
                    "url": url,
                    "salary_band": band,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "levels_fyi fetch failed company=%s role=%s exc=%s",
                company_slug, role_slug, exc,
            )
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
        s = (raw or "").strip().lower()
        if not s:
            return None
        # Strip URL prefixes if a full URL was passed.
        for prefix in ("https://", "http://", "www.", "levels.fyi/companies/"):
            if s.startswith(prefix):
                s = s[len(prefix):]
        s = s.strip("/").split("/", 1)[0].split("?", 1)[0]
        # Slugs use lowercase + hyphens; replace whitespace/underscores.
        cleaned_chars = []
        for c in s:
            if c.isalnum():
                cleaned_chars.append(c)
            elif c in "- _":
                cleaned_chars.append("-")
        cleaned = "".join(cleaned_chars).strip("-")
        # Collapse repeated hyphens.
        while "--" in cleaned:
            cleaned = cleaned.replace("--", "-")
        return cleaned or None

    @staticmethod
    def _is_blocked(html: str) -> bool:
        lower = html.lower()
        return any(marker in lower for marker in _BLOCK_MARKERS)

    @classmethod
    def _extract_band(cls, html: str) -> Optional[Dict[str, int]]:
        match = _NEXT_DATA_RE.search(html)
        if not match:
            return None
        blob = match.group("blob").strip()
        try:
            data = json.loads(blob)
        except (ValueError, TypeError):
            return None
        # Walk recursively for the first dict that contains percentile keys.
        found = _walk_for_percentiles(data)
        if not found:
            return None
        p25 = _coerce_money(_first_present(found, _P25_KEYS))
        p50 = _coerce_money(_first_present(found, _P50_KEYS))
        p75 = _coerce_money(_first_present(found, _P75_KEYS))
        # Require at least p50 to be useful.
        if p50 is None:
            return None
        band: Dict[str, int] = {"p50": p50}
        if p25 is not None:
            band["p25"] = p25
        if p75 is not None:
            band["p75"] = p75
        return band

    async def _get_client(self):
        if self._client is not None:
            return self._client, False
        import httpx
        headers = {
            "User-Agent": self._ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        return (
            httpx.AsyncClient(
                timeout=self._timeout_s, headers=headers, follow_redirects=True,
            ),
            True,
        )


def _walk_for_percentiles(node: Any, depth: int = 0) -> Optional[Dict[str, Any]]:
    """DFS for the first dict that exposes percentile fields."""
    if depth > 12:  # depth guard against pathological blobs
        return None
    if isinstance(node, dict):
        # Prefer nested explicit "percentiles"-shaped containers.
        for key in _PERCENTILE_KEYS:
            inner = node.get(key)
            if isinstance(inner, dict) and _has_percentile_fields(inner):
                return inner
        # Otherwise: this dict itself if it directly carries the fields.
        if _has_percentile_fields(node):
            return node
        for v in node.values():
            found = _walk_for_percentiles(v, depth + 1)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _walk_for_percentiles(item, depth + 1)
            if found:
                return found
    return None


def _has_percentile_fields(d: Dict[str, Any]) -> bool:
    return (
        _first_present(d, _P50_KEYS) is not None
        and (
            _first_present(d, _P25_KEYS) is not None
            or _first_present(d, _P75_KEYS) is not None
        )
    )


def _first_present(d: Dict[str, Any], keys: tuple) -> Any:
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return None


def _coerce_money(raw: Any) -> Optional[int]:
    """Convert strings like '$185,000' / '185k' / 185000 to int USD."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw) if raw > 0 else None
    if not isinstance(raw, str):
        return None
    s = raw.strip().replace("$", "").replace(",", "").lower()
    if not s:
        return None
    multiplier = 1
    if s.endswith("k"):
        multiplier = 1_000
        s = s[:-1]
    elif s.endswith("m"):
        multiplier = 1_000_000
        s = s[:-1]
    try:
        val = float(s)
    except ValueError:
        return None
    out = int(val * multiplier)
    return out if out > 0 else None
