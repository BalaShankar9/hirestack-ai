"""Deterministic per-document quality scoring.

Used by the Sentinel phase to produce a stable, cost-free quality signal for
every benchmark or tailored document we ship. Augments the LLM-driven
critique scores already produced by the agentic stack — this module is a
fast, free, offline floor that catches the obvious failure modes (empty
documents, broken HTML, ATS-hostile structure, missing JD keywords).

Design notes
------------
* Pure-function, no I/O, no LLM calls — safe to call in tight loops.
* Returns a 0-100 integer score plus a structured breakdown so callers
  can surface specific issues to the user.
* All thresholds are conservative — the floor we trust, not the ceiling.
* `score_document(html, doc_type, jd_keywords)` is the single public API.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional

# ── Per-doc length sweet-spots (chars) ────────────────────────────────
# Below `min_chars` → too thin to be useful. Above `max_chars` → bloated.
_LENGTH_BANDS: Dict[str, tuple[int, int]] = {
    "cv":                 (1500, 18000),
    "resume":             (800,  6500),
    "cover_letter":       (600,  4500),
    "personal_statement": (700,  5500),
    "portfolio":          (600,  9000),
    "learning_plan":      (500,  9000),
    # Catch-all for any other doc_type
    "_default":           (400, 12000),
}

# ── ATS-hostile patterns ──────────────────────────────────────────────
_ATS_HOSTILE_PATTERNS: List[tuple[str, re.Pattern[str]]] = [
    ("uses <img>",          re.compile(r"<img\b", re.IGNORECASE)),
    ("layout <table>",      re.compile(r"<table\b", re.IGNORECASE)),
    ("inline style attr",   re.compile(r"\sstyle\s*=", re.IGNORECASE)),
    ("script tag",          re.compile(r"<script\b", re.IGNORECASE)),
]

# ── Lightweight HTML structure checks ─────────────────────────────────
_HEADER_RE = re.compile(r"<h[1-6]\b", re.IGNORECASE)
_PARA_RE = re.compile(r"<p\b", re.IGNORECASE)
_LIST_RE = re.compile(r"<(ul|ol|li)\b", re.IGNORECASE)


def _strip_html(html: str) -> str:
    """Cheap text extraction — good enough for keyword coverage scoring."""
    if not html:
        return ""
    # Drop tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def _normalise_keywords(keywords: Optional[Iterable[str]]) -> List[str]:
    if not keywords:
        return []
    out: List[str] = []
    seen: set[str] = set()
    for kw in keywords:
        if not isinstance(kw, str):
            continue
        k = kw.strip().lower()
        if not k or k in seen or len(k) < 2:
            continue
        seen.add(k)
        out.append(k)
    return out[:40]  # cap


def score_document(
    html: str,
    doc_type: str = "_default",
    jd_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Score one document. Returns a stable structured dict.

    Parameters
    ----------
    html
        The document HTML (post-sanitisation is fine, sanitisation is not
        required — the scorer is pure-text and tolerant of either).
    doc_type
        Canonical doc type ("cv", "resume", "cover_letter", etc.). Drives
        the length band only. Unknown types fall back to a generous default.
    jd_keywords
        Iterable of JD keywords (any casing). Drives keyword coverage.
        Optional — if absent, keyword coverage scores neutral 1.0.

    Returns
    -------
    dict with keys:
        score:             int (0-100)
        length_ok:         bool
        structure_ok:      bool
        keyword_coverage:  float (0.0-1.0)
        ats_ok:            bool
        issues:            list[str]
        char_count:        int
        keyword_hits:      int
        keyword_total:     int
    """
    breakdown: Dict[str, Any] = {
        "score": 0,
        "length_ok": False,
        "structure_ok": False,
        "keyword_coverage": 0.0,
        "ats_ok": True,
        "issues": [],
        "char_count": 0,
        "keyword_hits": 0,
        "keyword_total": 0,
    }
    if not isinstance(html, str) or not html.strip():
        breakdown["issues"].append("empty document")
        return breakdown

    char_count = len(html)
    breakdown["char_count"] = char_count

    # ── Length band ───────────────────────────────────────────────
    band = _LENGTH_BANDS.get(doc_type, _LENGTH_BANDS["_default"])
    if char_count < band[0]:
        breakdown["issues"].append(f"too short ({char_count} < {band[0]})")
    elif char_count > band[1]:
        breakdown["issues"].append(f"too long ({char_count} > {band[1]})")
    else:
        breakdown["length_ok"] = True

    # ── Structure ────────────────────────────────────────────────
    has_header = bool(_HEADER_RE.search(html))
    has_para = bool(_PARA_RE.search(html))
    has_list = bool(_LIST_RE.search(html))
    if not has_header:
        breakdown["issues"].append("no <h1-6> headers")
    if not (has_para or has_list):
        breakdown["issues"].append("no <p>/<ul>/<ol> body content")
    breakdown["structure_ok"] = has_header and (has_para or has_list)

    # ── ATS hostility ────────────────────────────────────────────
    ats_issues: List[str] = []
    for label, pat in _ATS_HOSTILE_PATTERNS:
        if pat.search(html):
            ats_issues.append(f"ATS issue: {label}")
    if ats_issues:
        breakdown["ats_ok"] = False
        breakdown["issues"].extend(ats_issues)

    # ── Keyword coverage ─────────────────────────────────────────
    keywords = _normalise_keywords(jd_keywords)
    if keywords:
        text_lower = _strip_html(html).lower()
        hits = sum(1 for kw in keywords if kw in text_lower)
        breakdown["keyword_hits"] = hits
        breakdown["keyword_total"] = len(keywords)
        breakdown["keyword_coverage"] = round(hits / len(keywords), 3)
        if breakdown["keyword_coverage"] < 0.3:
            breakdown["issues"].append(
                f"low JD-keyword coverage ({hits}/{len(keywords)})"
            )
    else:
        # No JD keywords supplied — don't penalise.
        breakdown["keyword_coverage"] = 1.0
        breakdown["keyword_hits"] = 0
        breakdown["keyword_total"] = 0

    # ── Composite score ──────────────────────────────────────────
    # Weighted: length 25, structure 25, ATS 20, keywords 30.
    score = 0.0
    score += 25.0 if breakdown["length_ok"] else 10.0 if char_count >= 200 else 0.0
    score += 25.0 if breakdown["structure_ok"] else 12.0 if has_header or has_para else 0.0
    score += 20.0 if breakdown["ats_ok"] else max(0.0, 20.0 - 6.0 * len(ats_issues))
    score += 30.0 * breakdown["keyword_coverage"]
    breakdown["score"] = int(round(min(100.0, max(0.0, score))))

    return breakdown


def score_bundle(
    documents: Dict[str, str],
    jd_keywords: Optional[Iterable[str]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Score every document in a bundle. Returns {doc_type: breakdown}.

    `documents` is a dict mapping canonical doc_type → HTML. Empty/missing
    docs are skipped (not scored as 0 — that would distort the bundle
    average for un-requested modules).
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not isinstance(documents, dict):
        return out
    for doc_type, html in documents.items():
        if not isinstance(html, str) or not html.strip():
            continue
        out[doc_type] = score_document(html, doc_type=doc_type, jd_keywords=jd_keywords)
    return out


def aggregate_score(per_doc: Dict[str, Dict[str, Any]]) -> int:
    """Mean of per-doc scores, rounded. Empty bundle → 0."""
    if not per_doc:
        return 0
    scores = [int(v.get("score", 0)) for v in per_doc.values() if isinstance(v, dict)]
    if not scores:
        return 0
    return int(round(sum(scores) / len(scores)))
