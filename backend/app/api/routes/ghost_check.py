"""
Public ghost-check API — /api/ghost-check.

Purpose:
    Anonymous, rate-limited endpoint that takes a job posting URL and
    returns a PostingLegitimacy verdict. Designed as the public viral
    surface for HireStack AI:
      • No auth required (lowers friction for sharing).
      • Rate-limited by IP (5/min — generous for genuine usage,
        prohibitive for scraping).
      • Verdict cached in-process for 24h on canonical URL.

Companion endpoint /api/ghost-check/permalink/{hash} is added in a
follow-up slice (E1.c) once we have a public_scans persistence table.
For now this slice ships the verdict engine + an in-memory LRU cache,
which is enough for the route to be useful and observable.

Dependencies:
    - app.services.posting_legitimacy.evaluate_posting_legitimacy
    - app.services.url_canonicalizer.canonicalize_url
    - httpx for fetching the page (HEAD-then-GET, 5s budget)
    - slowapi limiter for IP-based throttling

The fetcher is intentionally minimal: HEAD for status, GET for body
(text only, max 256KB), one redirect, no JS execution. Modern ATS
pages are server-rendered enough for our heuristics to fire.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from typing import Optional, Tuple
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.security import limiter
from app.services.posting_legitimacy import evaluate_posting_legitimacy
from app.services.url_canonicalizer import canonicalize_url

logger = logging.getLogger("hirestack.ghost_check")
router = APIRouter()

# ── Fetcher constants ────────────────────────────────────────────────────
_FETCH_TIMEOUT_S = 5.0
_MAX_BODY_BYTES = 256 * 1024  # 256KB plenty for ATS pages
_USER_AGENT = (
    "HireStackBot/1.0 (+https://hirestack.ai/ghost-check; "
    "checks job posting legitimacy on user request)"
)
_ALLOWED_SCHEMES = frozenset({"http", "https"})

# Common apply-button text we extract from ATS pages.
# A focused HTML-token heuristic (NOT a full DOM parser) — pulls visible
# text from <a> and <button>, plus the value="..." of any
# <input type="submit"> regardless of attribute order.
_TEXT_TAG_RE = re.compile(
    r"<(?:a|button)\b[^>]*>([^<]{1,80})</(?:a|button)>",
    re.IGNORECASE,
)
_INPUT_SUBMIT_RE = re.compile(
    r'<input\b(?=[^>]*\btype=["\']submit["\'])(?=[^>]*\bvalue=["\']([^"\']{1,80})["\'])[^>]*>',
    re.IGNORECASE,
)
_TAG_STRIP_RE = re.compile(r"<[^>]+>")
_WS_COLLAPSE_RE = re.compile(r"\s+")


# ── In-process LRU cache ─────────────────────────────────────────────────
# Keyed on canonical URL. Tuple of (verdict_dict, expires_at_unix).
# Cap at 1024 entries — at 5 req/min/IP this is already > 1 hour of P99
# cache reuse. Real persistence is E1.c (public_scans table).
_CACHE_MAX = 1024
_CACHE_TTL_S = 24 * 3600
_cache: dict[str, Tuple[dict, float]] = {}
# Reverse index: url_hash → canonical URL, so GET /g/{hash} can fetch.
# Same lifecycle as _cache; pruned together.
_hash_index: dict[str, str] = {}
_cache_lock = asyncio.Lock()


async def _cache_get(key: str) -> Optional[dict]:
    async with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        verdict, expires_at = entry
        if time.time() >= expires_at:
            _cache.pop(key, None)
            # Also drop matching hash index entry, if any.
            for h, c in list(_hash_index.items()):
                if c == key:
                    _hash_index.pop(h, None)
            return None
        return verdict


async def _cache_put(key: str, verdict: dict) -> None:
    async with _cache_lock:
        if len(_cache) >= _CACHE_MAX:
            # Cheap eviction: drop oldest by expires_at.
            oldest_key = min(_cache, key=lambda k: _cache[k][1])
            _cache.pop(oldest_key, None)
            for h, c in list(_hash_index.items()):
                if c == oldest_key:
                    _hash_index.pop(h, None)
        _cache[key] = (verdict, time.time() + _CACHE_TTL_S)
        # Mirror into hash index.
        url_hash = verdict.get("url_hash")
        if url_hash:
            _hash_index[url_hash] = key


# ── HTML helpers ─────────────────────────────────────────────────────────
def extract_apply_controls(html: str) -> list[str]:
    """Pull visible <a>/<button>/<input type=submit> text from raw HTML.

    Returns up to 50 candidate strings (we only need 1 to match).
    Order-preserving, deduplicated. Pure function for testability.
    """
    seen: set[str] = set()
    out: list[str] = []
    for m in _TEXT_TAG_RE.finditer(html):
        text = (m.group(1) or "").strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text)
        if len(out) >= 50:
            break
    if len(out) < 50:
        for m in _INPUT_SUBMIT_RE.finditer(html):
            text = (m.group(1) or "").strip()
            if not text or text.lower() in seen:
                continue
            seen.add(text.lower())
            out.append(text)
            if len(out) >= 50:
                break
    return out


def extract_visible_text(html: str, max_chars: int = 8000) -> str:
    """Strip tags and collapse whitespace. Best-effort, no DOM parser."""
    no_tags = _TAG_STRIP_RE.sub(" ", html)
    cleaned = _WS_COLLAPSE_RE.sub(" ", no_tags).strip()
    return cleaned[:max_chars]


# ── Fetcher ──────────────────────────────────────────────────────────────
async def fetch_posting(url: str) -> Tuple[int, str, str]:
    """Fetch a posting URL with a strict budget.

    Returns (status_code, final_url, body_html). Never raises;
    on timeout/network error returns (0, url, "").
    """
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    try:
        async with httpx.AsyncClient(
            timeout=_FETCH_TIMEOUT_S,
            follow_redirects=True,
            max_redirects=3,
            headers=headers,
        ) as client:
            resp = await client.get(url)
            body = resp.text[:_MAX_BODY_BYTES]
            return resp.status_code, str(resp.url), body
    except httpx.HTTPError as exc:
        logger.warning("ghost_check_fetch_failed url=%s err=%s", url[:200], str(exc)[:200])
        return 0, url, ""


# ── Request/response models ──────────────────────────────────────────────
class GhostCheckRequest(BaseModel):
    url: str = Field(..., min_length=8, max_length=2048)

    @field_validator("url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("url is required")
        parsed = urlparse(v)
        if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
            raise ValueError("url must be http or https")
        if not parsed.netloc:
            raise ValueError("url must include a host")
        return v


def _hash_url(canonical: str) -> str:
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


# ── Routes ───────────────────────────────────────────────────────────────
@router.post("/ghost-check")
@limiter.limit("5/minute")
async def ghost_check(request: Request, body: GhostCheckRequest) -> dict:
    """Public, anonymous ghost-check.

    Returns a PostingLegitimacy verdict. Caches by canonical URL for 24h.
    """
    canonical = canonicalize_url(body.url)
    if not canonical:
        raise HTTPException(status_code=400, detail="Could not canonicalize URL")

    cached = await _cache_get(canonical)
    if cached is not None:
        return {**cached, "cached": True, "url_hash": _hash_url(canonical)}

    status_code, final_url, html = await fetch_posting(canonical)
    apply_controls = extract_apply_controls(html) if html else []
    body_text = extract_visible_text(html) if html else ""

    verdict = evaluate_posting_legitimacy(
        url=canonical,
        status=status_code,
        final_url=final_url,
        body_text=body_text,
        apply_controls=apply_controls,
    )
    payload = verdict.to_dict()
    payload["url_hash"] = _hash_url(canonical)
    await _cache_put(canonical, payload)
    return {**payload, "cached": False}


@router.get("/ghost-check/{url_hash}")
async def ghost_check_permalink(request: Request, url_hash: str) -> dict:
    """Fetch a previously-computed verdict by its short hash.

    Used by the public permalink page (/g/{hash} on the frontend) and
    by social previews. Returns 404 if the verdict has expired or was
    never computed; the frontend prompts the user to re-scan in that case.

    Persistence is currently in-process; surviving a redeploy requires
    the public_scans Supabase table (E1.c-v2 migration, follow-up slice).
    """
    if not url_hash or len(url_hash) != 16 or not all(
        c in "0123456789abcdef" for c in url_hash.lower()
    ):
        raise HTTPException(status_code=400, detail="Invalid hash format")

    async with _cache_lock:
        canonical = _hash_index.get(url_hash)
    if canonical is None:
        raise HTTPException(
            status_code=404,
            detail="Verdict not found or expired. Re-run the scan.",
        )
    cached = await _cache_get(canonical)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail="Verdict not found or expired. Re-run the scan.",
        )
    return {**cached, "cached": True}


__all__ = ["router", "extract_apply_controls", "extract_visible_text", "fetch_posting"]
