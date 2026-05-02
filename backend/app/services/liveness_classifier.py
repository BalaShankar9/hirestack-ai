"""
Liveness classifier — pure-Python, zero LLM, multilingual.

Classifies a fetched job-posting page into one of four liveness states
based on HTTP status, final URL, body text, and detected apply controls.
Designed for use by `posting_legitimacy.py` (E1.a) and the public
`/ghost-check` endpoint (E1.b).

Ported and extended from career-ops/liveness-core.mjs (MIT, 78 LOC).
Extensions over the upstream:
- Italian + Portuguese expired-banner patterns
- Apply-control patterns for Italian, Portuguese, Dutch
- Confidence score (0.0–1.0) per classification
- Transparent `signals` list for downstream legitimacy reasoning
- Structured `LivenessResult` dataclass

Precedence (first match wins):
    1. HTTP 404 / 410     → REMOVED  (1.0)
    2. Expired URL params → REMOVED  (0.95)
    3. Hard expired body  → REMOVED  (0.9)
    4. Visible apply ctrl → LIVE     (0.9)
    5. Listing-page bait  → REMOVED  (0.7)   (URL pretended to be a job, body is a search results page)
    6. Body < MIN_CHARS   → UNKNOWN  (0.5)   (likely SPA shell or login wall)
    7. Default            → UNKNOWN  (0.4)   (content present, no apply control)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Pattern, Sequence


class Liveness(str, Enum):
    """Liveness state for a fetched job posting."""

    LIVE = "live"          # Visible apply control found (still accepting apps)
    REMOVED = "removed"    # Posting was taken down or expired
    PAUSED = "paused"      # Reserved for future use (e.g. "applications temporarily closed")
    UNKNOWN = "unknown"    # Indeterminate — SPA shell, login wall, or ambiguous content


# ════════════════════════════════════════════════════════════════════════
# Pattern tables — multilingual, additive only.
# Adding a pattern: append; never reorder (precedence relies on order).
# Adding a language: add to ALL three tables (HARD_EXPIRED, APPLY, LISTING).
# ════════════════════════════════════════════════════════════════════════

# Hard signals that the posting is definitively closed.
# Sources: career-ops/liveness-core.mjs + extensions for it/pt/extra es/de.
HARD_EXPIRED_PATTERNS: tuple[Pattern[str], ...] = (
    # English
    re.compile(r"job (is )?no longer available", re.I),
    re.compile(r"job.*no longer open", re.I),
    re.compile(r"position has been filled", re.I),
    re.compile(r"this job has expired", re.I),
    re.compile(r"job posting has expired", re.I),
    re.compile(r"no longer accepting applications", re.I),
    re.compile(r"this (position|role|job) (is )?no longer", re.I),
    re.compile(r"this job (listing )?is closed", re.I),
    re.compile(r"job (listing )?not found", re.I),
    re.compile(r"the page you are looking for doesn.t exist", re.I),
    re.compile(r"applications?\s+(?:(?:have|are|is)\s+)?closed", re.I),
    re.compile(r"closed on \d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", re.I),
    re.compile(r"closed on (?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}", re.I),
    # German
    re.compile(r"diese stelle (ist )?(nicht mehr|bereits) besetzt", re.I),
    re.compile(r"stelle ist (nicht mehr verfügbar|bereits vergeben)", re.I),
    # French
    re.compile(r"offre (expirée|n'est plus disponible)", re.I),
    re.compile(r"poste (n'est plus disponible|a été pourvu)", re.I),
    # Spanish
    re.compile(r"(esta\s+)?(oferta|vacante|posición)\s+(ya\s+)?no\s+(est[áa]\s+)?(disponible|activa)", re.I),
    re.compile(r"plaza (cubierta|ya cubierta)", re.I),
    # Portuguese
    re.compile(r"(esta\s+)?vaga\s+(j[áa]\s+)?n[ãa]o\s+est[áa]\s+(dispon[íi]vel|ativa)", re.I),
    re.compile(r"vaga (encerrada|preenchida)", re.I),
    # Italian
    re.compile(r"(questa\s+)?(offerta|posizione)\s+(non è più disponibile|è scaduta|è chiusa)", re.I),
    re.compile(r"posizione (chiusa|coperta)", re.I),
    # Dutch
    re.compile(r"deze vacature is (niet meer beschikbaar|gesloten|vervuld)", re.I),
)

# URL-level signals (typically redirected error pages).
EXPIRED_URL_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"[?&]error=true", re.I),
    re.compile(r"[?&]expired=1", re.I),
    re.compile(r"/(404|expired|closed|not[-_]found)(/|$|\?)", re.I),
)

# Listing-page bait — URL looked like a job page but body shows search results.
LISTING_PAGE_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\d+\s+jobs?\s+found", re.I),
    re.compile(r"search for jobs page is loaded", re.I),
    re.compile(r"showing \d+\s*-\s*\d+ of \d+ (jobs|positions|results)", re.I),
)

# Visible apply-control text (button labels, link text, ARIA labels).
APPLY_PATTERNS: tuple[Pattern[str], ...] = (
    re.compile(r"\bapply\b", re.I),                 # English
    re.compile(r"\bsolicitar\b", re.I),             # Spanish
    re.compile(r"\bbewerben\b", re.I),              # German
    re.compile(r"\bpostuler\b", re.I),              # French
    re.compile(r"submit application", re.I),
    re.compile(r"easy apply", re.I),
    re.compile(r"start application", re.I),
    re.compile(r"ich bewerbe mich", re.I),          # German "I'm applying"
    re.compile(r"\bcandidatar(?:-se)?\b", re.I),    # Portuguese
    re.compile(r"\bcandidati\b", re.I),             # Italian
    re.compile(r"\binvia candidatura\b", re.I),     # Italian
    re.compile(r"\bsolliciteer\b", re.I),           # Dutch
    re.compile(r"\bаpply\s+now\b", re.I),
    re.compile(r"apply for this (job|role|position)", re.I),
)

# Below this body length we assume SPA shell or login-walled content.
MIN_CONTENT_CHARS: int = 300


# ════════════════════════════════════════════════════════════════════════
# Result dataclass
# ════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class LivenessResult:
    """Outcome of classify_liveness().

    Attributes:
        liveness:    Final classification (Liveness enum value).
        reason:      Human-readable explanation; safe for UI display.
        confidence:  0.0–1.0; how strongly the signals support this classification.
        signals:     Ordered list of every matched pattern / signal name. Used by
                     posting_legitimacy.py to build the legitimacy report.
    """

    liveness: Liveness
    reason: str
    confidence: float
    signals: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        """JSON-serializable dict for SSE meta + API responses."""
        return {
            "liveness": self.liveness.value,
            "reason": self.reason,
            "confidence": self.confidence,
            "signals": list(self.signals),
        }


# ════════════════════════════════════════════════════════════════════════
# Internal helpers
# ════════════════════════════════════════════════════════════════════════


def _first_match(patterns: Iterable[Pattern[str]], text: str) -> Pattern[str] | None:
    """Return the first compiled pattern that matches text, or None."""
    if not text:
        return None
    for pattern in patterns:
        if pattern.search(text):
            return pattern
    return None


def _has_apply_control(controls: Sequence[str]) -> Pattern[str] | None:
    """Return the first APPLY_PATTERN matching any control label, or None."""
    if not controls:
        return None
    for control in controls:
        if not control:
            continue
        match = _first_match(APPLY_PATTERNS, control)
        if match is not None:
            return match
    return None


# ════════════════════════════════════════════════════════════════════════
# Public API
# ════════════════════════════════════════════════════════════════════════


def classify_liveness(
    *,
    status: int = 0,
    final_url: str = "",
    body_text: str = "",
    apply_controls: Sequence[str] = (),
) -> LivenessResult:
    """Classify a fetched job posting page into a liveness state.

    Args:
        status:         HTTP status code from the final response.
        final_url:      The URL after any redirects.
        body_text:      Visible text content of the page (no HTML).
        apply_controls: Text from buttons/links that look like apply
                        actions. Pre-extracted by the caller (e.g. via
                        Playwright `[role=button]` text).

    Returns:
        LivenessResult — never raises; pure function.
    """
    signals: list[str] = []

    # 1. HTTP terminal codes — definitive removed signal.
    if status in (404, 410):
        signals.append(f"http_{status}")
        return LivenessResult(
            liveness=Liveness.REMOVED,
            reason=f"HTTP {status}",
            confidence=1.0,
            signals=tuple(signals),
        )

    # 2. URL-level expired markers (error redirects).
    url_match = _first_match(EXPIRED_URL_PATTERNS, final_url)
    if url_match is not None:
        signals.append(f"expired_url:{url_match.pattern}")
        return LivenessResult(
            liveness=Liveness.REMOVED,
            reason=f"redirect to error URL: {final_url}",
            confidence=0.95,
            signals=tuple(signals),
        )

    # 3. Hard expired phrases in body — these BEAT generic apply text
    #    (a banner saying "this job is closed" with a leftover Apply
    #    button is removed, not live).
    body_match = _first_match(HARD_EXPIRED_PATTERNS, body_text)
    if body_match is not None:
        signals.append(f"expired_phrase:{body_match.pattern}")
        return LivenessResult(
            liveness=Liveness.REMOVED,
            reason=f"expired-banner phrase matched: {body_match.pattern}",
            confidence=0.9,
            signals=tuple(signals),
        )

    # 4. Visible apply control — strongest live signal we can derive
    #    from a pre-rendered page.
    apply_match = _has_apply_control(apply_controls)
    if apply_match is not None:
        signals.append(f"apply_control:{apply_match.pattern}")
        return LivenessResult(
            liveness=Liveness.LIVE,
            reason="visible apply control detected",
            confidence=0.9,
            signals=tuple(signals),
        )

    # 5. Listing-page bait — URL pointed at a single job but body is a
    #    search results page (ATS often does this when the job is gone).
    listing_match = _first_match(LISTING_PAGE_PATTERNS, body_text)
    if listing_match is not None:
        signals.append(f"listing_page:{listing_match.pattern}")
        return LivenessResult(
            liveness=Liveness.REMOVED,
            reason=f"listing-page pattern matched: {listing_match.pattern}",
            confidence=0.7,
            signals=tuple(signals),
        )

    # 6. Insufficient content — likely SPA shell or login/captcha wall.
    if len(body_text.strip()) < MIN_CONTENT_CHARS:
        signals.append(f"thin_content:{len(body_text.strip())}_chars")
        return LivenessResult(
            liveness=Liveness.UNKNOWN,
            reason="insufficient content — likely nav/footer only or SPA shell",
            confidence=0.5,
            signals=tuple(signals),
        )

    # 7. Default — content is present but we couldn't find an apply
    #    control. Could be a live posting where the apply button is
    #    rendered server-side after auth, or a dead one. UNKNOWN.
    signals.append("no_apply_control_found")
    return LivenessResult(
        liveness=Liveness.UNKNOWN,
        reason="content present but no visible apply control found",
        confidence=0.4,
        signals=tuple(signals),
    )


__all__ = [
    "Liveness",
    "LivenessResult",
    "classify_liveness",
    "HARD_EXPIRED_PATTERNS",
    "EXPIRED_URL_PATTERNS",
    "LISTING_PAGE_PATTERNS",
    "APPLY_PATTERNS",
    "MIN_CONTENT_CHARS",
]
