"""Phase C.2 — derive style signals from a successful pipeline run.

Reads the final draft content + critic scores + enriched context, and
extracts conservative style signals (tone, length, preferred_keywords,
avoid_phrases) that get folded into the agent_memory blob.

Design constraints:
- Only emit signals when the run was actually good (avg quality ≥ 75
  and no fabrication flags) so we don't poison memory with bad runs.
- Conservative thresholds — better to skip a signal than record a false
  one.  A skipped run is harmless; a false signal ranks the next run.
- Pure functions, no I/O.  Caller is responsible for storage.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional

# Words too common to be useful as preference signals.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "have", "in", "is", "it", "its", "of", "on", "or", "that", "the", "to",
    "was", "were", "will", "with", "you", "your", "we", "our", "they", "this",
    "their", "i", "me", "my", "but", "if", "so", "all", "any", "can", "do",
    "had", "her", "him", "his", "how", "may", "more", "no", "not", "now",
    "out", "than", "them", "these", "those", "what", "when", "where", "which",
    "who", "whom", "whose", "why", "would", "should", "could", "very", "much",
    "some", "such", "also", "other", "into", "over", "after", "before", "while",
})

# Quality bar a run must clear to contribute style signals.
_MIN_AVG_QUALITY: float = 75.0
_MIN_TONE_MATCH: float = 75.0  # tone signal needs the tone-match dim to clear

# Length buckets (word counts).  Tuned to typical outputs:
# - cover letter ~250-400, motivation ~300-500, CV ~300-800.
# Buckets are document-type-agnostic on purpose; the bucket itself
# (short/medium/long) is what feeds back into the next prompt.
_LENGTH_BUCKETS = (
    ("short",  0,    250),
    ("medium", 250,  500),
    ("long",   500,  10_000),
)


def _word_count(text: Any) -> int:
    if not isinstance(text, str):
        return 0
    return len(re.findall(r"\b\w[\w'-]*\b", text))


def _bucket_length(words: int) -> Optional[str]:
    for name, lo, hi in _LENGTH_BUCKETS:
        if lo <= words < hi:
            return name
    return None


def _tokenize(text: str) -> List[str]:
    return [
        t.lower() for t in re.findall(r"\b[a-zA-Z][a-zA-Z+#.-]{2,}\b", text)
    ]


def _extract_jd_keywords(jd_text: str, *, top_n: int = 12) -> List[str]:
    if not jd_text:
        return []
    tokens = _tokenize(jd_text)
    counter = Counter(t for t in tokens if t not in _STOPWORDS and len(t) > 3)
    return [t for t, _ in counter.most_common(top_n)]


def _avg_quality(scores: Optional[Dict[str, Any]]) -> float:
    if not isinstance(scores, dict) or not scores:
        return 0.0
    dims = ("impact", "clarity", "tone_match", "completeness")
    vals = [float(scores.get(d, 0) or 0) for d in dims]
    return sum(vals) / len(dims)


def _infer_tone_from_jd(jd_text: str) -> Optional[str]:
    """Cheap keyword-based tone classifier.  Only returns a tone when
    the signal is strong (multiple matches in one bucket and no rivals)."""
    if not jd_text:
        return None
    text = jd_text.lower()
    formal_hits = sum(text.count(k) for k in (
        "regulated", "compliance", "fortune", "governance", "stakeholder",
        "board", "director", "executive", "enterprise",
    ))
    technical_hits = sum(text.count(k) for k in (
        "kubernetes", "kafka", "rust", "golang", "scalability", "throughput",
        "latency", "distributed", "microservices", "observability",
    ))
    conversational_hits = sum(text.count(k) for k in (
        "fast-paced", "startup", "founders", "scrappy", "wear many hats",
        "small team", "disrupt",
    ))
    scores = {
        "formal": formal_hits,
        "technical": technical_hits,
        "conversational": conversational_hits,
    }
    top = max(scores.items(), key=lambda kv: kv[1])
    if top[1] < 2:
        return None
    # require a clear winner — at least double the runner-up
    others = sorted((v for k, v in scores.items() if k != top[0]), reverse=True)
    if others and top[1] < others[0] * 2:
        return None
    return top[0]


def derive_style_signals(
    *,
    draft_content: Any,
    critic_quality_scores: Optional[Dict[str, Any]],
    fact_check_summary: Optional[Dict[str, Any]] = None,
    enriched_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Extract a forward-compatible style-signals dict from a successful
    pipeline run.  Returns {} (not None) when no signals could be safely
    derived, so callers can ``learning.update(...)`` unconditionally.
    """
    # Quality gate — never learn from a mediocre or fabricated run.
    if _avg_quality(critic_quality_scores) < _MIN_AVG_QUALITY:
        return {}
    if isinstance(fact_check_summary, dict) and (fact_check_summary.get("fabricated") or 0) > 0:
        return {}

    signals: Dict[str, Any] = {}

    # ── Length ────────────────────────────────────────────────────────
    text_payload = ""
    if isinstance(draft_content, str):
        text_payload = draft_content
    elif isinstance(draft_content, dict):
        for key in ("content", "markdown", "text", "body"):
            v = draft_content.get(key)
            if isinstance(v, str) and v.strip():
                text_payload = v
                break
    words = _word_count(text_payload)
    if words >= 50:  # ignore truncated/empty drafts
        bucket = _bucket_length(words)
        if bucket:
            signals["length"] = bucket

    # ── Tone (only when critic confirms tone-match was strong) ────────
    ctx = enriched_context or {}
    tone_match = float((critic_quality_scores or {}).get("tone_match", 0) or 0)
    if tone_match >= _MIN_TONE_MATCH:
        jd_text = str(ctx.get("jd_text") or ctx.get("jdText") or "")
        inferred = _infer_tone_from_jd(jd_text)
        if inferred:
            signals["tone"] = inferred

    # ── Preferred keywords: JD top-N intersected with what made it
    # into the final draft.  These are the keywords that survived
    # critic + (optional) revision, so they're the ones we should
    # reinforce in the next run.
    jd_text = str(ctx.get("jd_text") or ctx.get("jdText") or "")
    if jd_text and text_payload:
        jd_top = _extract_jd_keywords(jd_text, top_n=15)
        draft_lower = text_payload.lower()
        kept = [kw for kw in jd_top if kw in draft_lower]
        if len(kept) >= 3:
            signals["preferred_keywords"] = kept[:8]

    return signals
