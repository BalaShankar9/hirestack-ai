"""
Evidence post-processing: dedup, rank, per-source cap.

The intel pipeline throws a lot of raw evidence at the profile LLM. Without
post-processing, the LLM sees near-duplicate strings (same press snippet
picked up by two providers), is biased toward whichever source happened to
produce the most items, and wastes context on low-signal rows. This module
fixes that before evidence reaches synthesis.

Public API:
  process_evidence(items, *, max_total=60, max_per_source=8) -> list[dict]

Pure-python, zero dependencies. Deterministic given the same inputs.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any


# Tiers reflect how we picked the evidence up. VERBATIM outranks DERIVED
# which outranks inferred.
_TIER_WEIGHT = {
    "VERBATIM": 3.0,
    "DERIVED": 2.0,
    "INFERRED": 1.0,
}


def _normalise_fact(fact: str) -> str:
    """Lowercase + collapse whitespace + strip leading page tags like '[about]'."""
    if not fact:
        return ""
    s = fact.strip().lower()
    # Drop leading '[label]' marker used by website sub-agent
    s = re.sub(r"^\[[^\]]{1,40}\]\s*", "", s)
    s = re.sub(r"\s+", " ", s)
    # Drop trailing ellipses and separators
    s = s.rstrip(" .…-–—:;,")
    return s


def _fact_signature(fact: str) -> str:
    """
    Short stable hash for near-dup detection. Uses the first 160 normalised
    characters so we collapse rows that differ only in trailing trivia.
    """
    norm = _normalise_fact(fact)[:160]
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _source_bucket(source: str) -> str:
    """
    Map a source label ('website:about', 'wiki:Stripe', 'search:techcrunch.com')
    to a coarser bucket used for per-source caps.
    """
    if not source:
        return "unknown"
    low = source.lower()
    # website:<page> → website
    if low.startswith("website:"):
        return "website"
    if low.startswith("github:"):
        return "github"
    if low.startswith("wiki:") or "wikipedia" in low:
        return "wikipedia"
    if low.startswith("careers:"):
        return "careers"
    if low.startswith("jd:"):
        return "jd"
    if low.startswith("search:"):
        # search:techcrunch.com → techcrunch.com
        host = low.split(":", 1)[1].strip()
        host = host.split("/", 1)[0]
        return f"web:{host}" if host else "web"
    return low.split(":", 1)[0] or low


# Known high-credibility hosts (for web: buckets) get a small bonus.
_HIGH_CREDIBILITY_HOSTS = {
    "techcrunch.com", "bloomberg.com", "reuters.com", "wsj.com",
    "ft.com", "nytimes.com", "forbes.com", "theverge.com",
    "arstechnica.com", "businessinsider.com", "cnbc.com",
    "github.com", "linkedin.com",
    "crunchbase.com",
}


def _score(item: dict) -> float:
    """
    Compute a rank score. Higher = keep preferentially.

    Factors:
      - Tier weight (VERBATIM > DERIVED > INFERRED).
      - Known host bonus (+0.5 for high-credibility outlets).
      - Freshness bonus (+0.5 if < 180 days old).
      - Fact length (tiny nudge: prefer meaty facts up to a cap).
    """
    tier = (item.get("tier") or "").upper()
    score = _TIER_WEIGHT.get(tier, 1.5)

    bucket = _source_bucket(item.get("source") or "")
    if bucket.startswith("web:"):
        host = bucket.split(":", 1)[1]
        if host in _HIGH_CREDIBILITY_HOSTS:
            score += 0.5
    elif bucket in ("website", "github", "careers", "jd"):
        # First-party signals are premium.
        score += 0.5

    days = item.get("days_since_published")
    if isinstance(days, int) and days >= 0:
        if days <= 30:
            score += 0.6
        elif days <= 180:
            score += 0.3

    fact = item.get("fact") or ""
    L = len(fact)
    if L >= 40:
        score += min(0.4, L / 2000.0)  # small length bonus capped at +0.4

    # Penalise generic boilerplate
    low = fact.lower()
    if "cookie" in low or "privacy policy" in low or "terms of service" in low:
        score -= 1.0

    return score


def process_evidence(
    items: list[dict],
    *,
    max_total: int = 60,
    max_per_source: int = 8,
) -> list[dict]:
    """
    Deduplicate, rank, and cap evidence items.

    Steps:
      1. Drop items with empty or boilerplate `fact` text.
      2. Group by signature (normalised + hashed first 160 chars). Keep the
         highest-scoring representative in each group; attach a
         `duplicate_count` so downstream can see signal strength.
      3. Apply per-source bucket cap.
      4. Sort by score desc, truncate to `max_total`.

    Input is not mutated. Output items are shallow copies with a
    `rank_score` field added for transparency.
    """
    if not items:
        return []

    # Step 1: filter trivially-bad rows.
    filtered: list[dict] = []
    for it in items:
        fact = (it.get("fact") or "").strip()
        if len(fact) < 8:
            continue
        filtered.append(it)

    # Step 2: dedup by signature, keeping the best representative.
    by_sig: dict[str, dict] = {}
    for it in filtered:
        sig = _fact_signature(it.get("fact") or "")
        s = _score(it)
        existing = by_sig.get(sig)
        if existing is None:
            rep = {**it, "rank_score": round(s, 3), "duplicate_count": 1}
            by_sig[sig] = rep
        else:
            existing["duplicate_count"] = int(existing.get("duplicate_count", 1)) + 1
            if s > float(existing.get("rank_score", 0)):
                # Preserve duplicate_count from existing, use the better row.
                dc = existing["duplicate_count"]
                replacement = {**it, "rank_score": round(s, 3), "duplicate_count": dc}
                by_sig[sig] = replacement

    deduped = list(by_sig.values())

    # Step 3: per-source bucket cap.
    # Sort globally by score first so each bucket keeps its top items.
    deduped.sort(key=lambda d: d.get("rank_score", 0), reverse=True)
    per_bucket: dict[str, int] = {}
    capped: list[dict] = []
    for it in deduped:
        bucket = _source_bucket(it.get("source") or "")
        used = per_bucket.get(bucket, 0)
        if used >= max_per_source:
            continue
        per_bucket[bucket] = used + 1
        capped.append(it)

    # Step 4: truncate to max_total (already sorted by score).
    return capped[: max(0, int(max_total))]


def summarise_evidence(items: list[dict]) -> dict[str, Any]:
    """Return a small breakdown suitable for logging/telemetry."""
    if not items:
        return {"count": 0}
    buckets: dict[str, int] = {}
    tiers: dict[str, int] = {}
    dup_total = 0
    for it in items:
        b = _source_bucket(it.get("source") or "")
        buckets[b] = buckets.get(b, 0) + 1
        t = (it.get("tier") or "UNKNOWN").upper()
        tiers[t] = tiers.get(t, 0) + 1
        dup_total += int(it.get("duplicate_count", 1))
    return {
        "count": len(items),
        "by_source_bucket": buckets,
        "by_tier": tiers,
        "total_duplicates_folded": dup_total,
    }
