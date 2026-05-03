"""
Public JD anti-pattern check API — /api/jd-check.

Anonymous, rate-limited endpoint that takes a job description blob and
returns the AntiPatternReport from E3.core jd_anti_pattern_detector.
Designed as the second public viral surface (sibling of /api/ghost-check).

Why anonymous + rate-limited:
  - Lowers friction for sharing on Twitter/LinkedIn
  - Rate-limited by IP (10/min — JDs are local input, no fetch budget
    needed, so we can afford slightly more than ghost-check's 5/min)
  - Hard input cap (200KB) so a single request can't tarpit a worker

What this route does NOT do:
  - No fetching (caller pastes the text — there's no URL)
  - No caching (output is deterministic given input; cheaper to re-run
    than to manage a cache invalidation story)
  - No persistence (a future E3.api.persist slice could log scans for
    SEO-permalink, mirroring E1.c-v2 — out of scope here)

Composition:
  - app.services.jd_anti_pattern_detector.detect_anti_patterns
  - slowapi limiter for IP throttling

Response shape mirrors AntiPatternReport: findings list with
{category, severity, snippet, term, char_start, char_end} dicts plus
top-level by_category, severity_counts, total_count.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.core.security import limiter
from app.services.jd_anti_pattern_detector import (
    AntiPatternReport,
    Finding,
    detect_anti_patterns,
)

logger = logging.getLogger("hirestack.jd_check")
router = APIRouter()

# ── Tunables ─────────────────────────────────────────────────────────
# JDs in the wild rarely exceed 12-15KB; 200KB is a generous cap that
# still bounds worst-case regex CPU. (All E3.core regexes are linear-
# scan with bounded backtracking.)
_MAX_JD_BYTES: int = 200 * 1024


# ── Request / response models ────────────────────────────────────────


class JDCheckRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=_MAX_JD_BYTES)

    @field_validator("text")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("text must not be empty")
        return v


def _finding_to_dict(f: Finding) -> dict:
    return {
        "category": f.category,
        "severity": f.severity,
        "snippet": f.snippet,
        "term": f.term,
        "char_start": f.char_start,
        "char_end": f.char_end,
    }


def _report_to_dict(r: AntiPatternReport) -> dict:
    return {
        "findings": [_finding_to_dict(f) for f in r.findings],
        "by_category": dict(r.by_category),
        "severity_counts": dict(r.severity_counts),
        "total_count": r.total_count,
    }


# ── Routes ───────────────────────────────────────────────────────────


@router.post("/jd-check")
@limiter.limit("10/minute")
async def jd_check(request: Request, body: JDCheckRequest) -> dict:
    """Public, anonymous JD anti-pattern scan.

    Returns an AntiPatternReport-shaped dict. Pure function under the
    hood — same input always yields same output.
    """
    try:
        report = detect_anti_patterns(body.text)
    except TypeError:
        # detect_anti_patterns only raises TypeError on non-str input,
        # which Pydantic should have caught — but be defensive at the
        # service boundary anyway.
        raise HTTPException(status_code=422, detail="text must be a string")

    return _report_to_dict(report)


__all__ = ["router"]
