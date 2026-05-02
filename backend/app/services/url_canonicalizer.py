"""URL canonicalization for job-posting dedup and repost detection.

Strips tracking parameters (utm_*, gh_src, fbclid, gclid, ref, ...),
lowercases scheme and host, removes trailing slashes on non-root paths,
and drops URL fragments.

Also provides ``extract_ats_key(url) -> (platform, company, job_id)``
for the six ATS platforms career-ops / HireStack already detect:
Greenhouse, Lever, Ashby, Workday, Workable, SmartRecruiters.

These primitives power:
  • ghost-job repost detection (`job_scan_history.url_canonical`)
  • application dedup (prevent duplicate apps for the same posting)
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Tracking parameters to strip (case-insensitive)
_TRACKING_PARAMS: frozenset[str] = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gh_src", "gh_jid", "gclid", "fbclid", "mc_cid", "mc_eid",
    "ref", "referrer", "source", "src", "_ga", "_gl",
})

# (platform, regex) — first match wins. Order matters where patterns could overlap.
_ATS_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("greenhouse",      re.compile(r"boards\.greenhouse\.io/([^/]+)/jobs/(\d+)")),
    ("lever",           re.compile(r"jobs\.lever\.co/([^/]+)/([^/?#]+)")),
    ("ashby",           re.compile(r"jobs\.ashbyhq\.com/([^/]+)/([^/?#]+)")),
    # Workday: subdomain.myworkdayjobs.com/.../job/.../<job_id>
    # Use [^./]+ so the scheme://... prefix doesn't leak into the capture.
    ("workday",         re.compile(r"([^./]+)\.myworkdayjobs\.com/[^/]+/job/[^/]+/([^/?#]+)")),
    ("workable",        re.compile(r"apply\.workable\.com/([^/]+)/j/([^/?#]+)")),
    ("smartrecruiters", re.compile(r"jobs\.smartrecruiters\.com/([^/]+)/([^/?#]+)")),
]


def canonicalize_url(url: str) -> str:
    """Normalize a URL for dedup / repost detection.

    Rules:
      1. Lowercase scheme and host (path case preserved — some ATSes use
         case-sensitive job IDs).
      2. Strip known tracking query-string parameters (case-insensitive name match).
      3. Drop URL fragment (``#apply`` etc.).
      4. Strip trailing slash on non-root paths (keep ``/`` for bare hosts).
      5. Leave unknown parameters intact (they may be meaningful, e.g. team filters).

    Returns ``""`` for empty input. Does not attempt to infer a missing scheme.
    """
    if not url:
        return url
    parsed = urlparse(url.strip())
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()

    # Path normalization: strip trailing slash except when path is bare root.
    path = parsed.path
    if path and path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    # Query normalization: drop tracking params, preserve order of the rest.
    kept_pairs = [
        (k, v)
        for k, v in parse_qsl(parsed.query, keep_blank_values=False)
        if k.lower() not in _TRACKING_PARAMS
    ]
    query = urlencode(kept_pairs)

    # Fragment is always dropped.
    return urlunparse((scheme, netloc, path, "", query, ""))


def extract_ats_key(url: str) -> Optional[tuple[str, str, str]]:
    """Return ``(platform, company, job_id)`` if ``url`` matches a known ATS pattern.

    Works on raw or canonicalized URLs — the regexes don't rely on query strings.
    Returns ``None`` for unknown hosts or empty input.
    """
    if not url:
        return None
    for platform, pattern in _ATS_PATTERNS:
        match = pattern.search(url)
        if match:
            return (platform, match.group(1), match.group(2))
    return None


__all__ = ["canonicalize_url", "extract_ats_key"]
