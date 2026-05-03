"""E3.core — JD anti-pattern detector (pure-function).

Paste a job-description blob → flag ageist, gendered, vague-compensation,
unrealistic-experience, culture-red-flag, and urgency language. No LLM,
no DB, no I/O. Pure regex tables + a tiny scorer; deterministic.

Why pure: the patterns are well-known recruiter anti-patterns documented
across (Textio, Atlassian, Wirecutter, Stack Overflow Jobs autopsy posts).
Encoding them as a regex table is more honest than asking an LLM to
"feel for bias" — and lets candidates AND employers see the same verdict
on the same input every time. This is the SEO surface E3 needs.

Surface (consumed by the future POST /api/jd-check route):
  - ``Finding(category, severity, snippet, term, char_start, char_end)``
  - ``AntiPatternReport(findings, by_category, total_count, severity_counts)``
  - ``detect_anti_patterns(jd_text) -> AntiPatternReport``

Severity ladder (matches insights_blockers vocabulary):
  - ``critical`` — illegal/discriminatory in most US/EU jurisdictions
                   (age + gender protected classes)
  - ``warn``     — culturally hostile or compensation-opaque
                   (drives down applicant pool quality silently)
  - ``info``     — context-dependent yellow flag (urgency, vague exp)

Snippets: each finding carries the ±60-char window around the matched
term so the UI can highlight in context. Char offsets are over the
ORIGINAL text (not lowercased) so the route can underline accurately.

What this slice does NOT do (deferred):
  - year-aware unrealistic-stack detection ("10+ years React" when React
    is 12 years old) — needs a tech_first_release_year table; ships as
    E3.core.years follow-up
  - language detection (English-only patterns for now; mirrors F3
    liveness where multilingual landed in a follow-up)
  - severity weighting beyond bucket counts (no overall 0-100 score yet)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final, Literal

# ── Public surface ────────────────────────────────────────────────────

AntiPatternCategory = Literal[
    "ageist",
    "gendered",
    "vague_compensation",
    "unrealistic_experience",
    "culture_red_flag",
    "urgency",
]

AntiPatternSeverity = Literal["critical", "warn", "info"]

# Ordering for UI: critical first, then warn, then info; within a bucket
# we preserve detection order (= source-text order) so the user reads
# top-to-bottom of the JD without jumping.
_SEVERITY_RANK: Final[dict[str, int]] = {"critical": 0, "warn": 1, "info": 2}

# Tunables
SNIPPET_RADIUS: Final[int] = 60      # chars on each side of match
UNREALISTIC_YEARS_THRESHOLD: Final[int] = 15  # "N+ years" with N >= this → warn
MAX_SNIPPET_LEN: Final[int] = 200    # safety cap for malformed input


@dataclass(frozen=True)
class Finding:
    category: AntiPatternCategory
    severity: AntiPatternSeverity
    snippet: str
    term: str
    char_start: int
    char_end: int


@dataclass(frozen=True)
class AntiPatternReport:
    findings: tuple[Finding, ...]
    by_category: dict[AntiPatternCategory, int]
    total_count: int
    severity_counts: dict[AntiPatternSeverity, int]


# ── Regex tables ──────────────────────────────────────────────────────
#
# Each entry: (compiled regex, term-label, severity).
# Patterns use word boundaries so "rockstart" doesn't false-match "rockstar".
# Case-insensitive throughout — JDs mix sentence/title case.

# Ageist: protected class in US (ADEA, age 40+) and EU. "Digital native" is
# the EEOC's textbook example — it's literally cited in the EEOC guidance.
_AGEIST: Final[tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]] = (
    (re.compile(r"\bdigital native[s]?\b", re.IGNORECASE), "digital native", "critical"),
    (re.compile(r"\byoung[, ]+(?:dynamic|energetic|fun|hungry|talented)\b", re.IGNORECASE), "young + adjective", "critical"),
    (re.compile(r"\b(?:dynamic|energetic|fun|hungry)[, ]+young\b", re.IGNORECASE), "young + adjective", "critical"),
    (re.compile(r"\byoung team\b", re.IGNORECASE), "young team", "critical"),
    (re.compile(r"\brecent grad(?:uate)?s? only\b", re.IGNORECASE), "recent grads only", "critical"),
    (re.compile(r"\bmax(?:imum)? \d+ years? (?:of )?experience\b", re.IGNORECASE), "experience cap", "critical"),
    (re.compile(r"\bno more than \d+ years?\b", re.IGNORECASE), "experience cap", "critical"),
    (re.compile(r"\bfresh (?:grad|out of (?:college|school|university))\b", re.IGNORECASE), "fresh grad only", "warn"),
)

# Gendered: "rockstar/ninja/guru" tested by Textio across 25k JDs to skew
# applicants ~20% male. "Manpower/he-or-she/salesman" are direct hits.
_GENDERED: Final[tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]] = (
    (re.compile(r"\brockstar(?!s? band)\b", re.IGNORECASE), "rockstar", "critical"),
    (re.compile(r"\bninja(?!\s+(?:turtle|warrior))\b", re.IGNORECASE), "ninja", "critical"),
    (re.compile(r"\b(?:code |coding )?guru[s]?\b", re.IGNORECASE), "guru", "critical"),
    (re.compile(r"\b(?:tech |coding )wizard[s]?\b", re.IGNORECASE), "wizard", "warn"),
    (re.compile(r"\bsalesman\b", re.IGNORECASE), "salesman", "critical"),
    (re.compile(r"\bmanpower\b", re.IGNORECASE), "manpower", "critical"),
    (re.compile(r"\bhe[/\\]she\b", re.IGNORECASE), "he/she", "warn"),
    (re.compile(r"\bhis[/\\]her\b", re.IGNORECASE), "his/her", "warn"),
    (re.compile(r"\bhey guys\b", re.IGNORECASE), "guys (informal)", "warn"),
)

# Vague comp: signal that the recruiter expects you to negotiate against
# yourself. "Competitive" with no number is the hallmark.
_VAGUE_COMP: Final[tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]] = (
    (re.compile(r"\bcompetitive (?:salary|compensation|pay|package)\b", re.IGNORECASE), "competitive (no number)", "warn"),
    (re.compile(r"\bsalary commensurate with experience\b", re.IGNORECASE), "salary commensurate", "warn"),
    (re.compile(r"\bdoe\b(?!\s*(?:v\.|case|john))", re.IGNORECASE), "DOE (depending on experience)", "warn"),
    (re.compile(r"\bequity in lieu of (?:salary|cash)\b", re.IGNORECASE), "equity in lieu of cash", "critical"),
    (re.compile(r"\bunpaid (?:internship|trial|position)\b", re.IGNORECASE), "unpaid", "critical"),
    (re.compile(r"\bfor exposure\b", re.IGNORECASE), "for exposure", "warn"),
)

# Unrealistic experience: "N+ years" with N >= UNREALISTIC_YEARS_THRESHOLD
# is per-se warn (15 years in any individual tool is a tell). Year-aware
# detection (e.g. "10 years React" when React is 12) is deferred.
_UNREALISTIC_EXP: Final[tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]] = (
    # We capture the digits group so the scorer can decide warn vs nothing.
    (re.compile(r"\b(\d{2,})\+?\s*(?:years?|yrs?)\b", re.IGNORECASE), "high year count", "warn"),
)

# Culture red flags: the "we're a family" / "wear many hats" cluster
# correlates with burnout-and-replace cultures (Glassdoor + leaver-survey
# data). Down-graded to warn because a small startup using "wear many hats"
# is also literal — context matters. Critical only when paired ("rockstar
# culture", "family-style hours").
_CULTURE: Final[tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]] = (
    (re.compile(r"\bwe(?:'re|\sare)\s+(?:a |one big )?family\b", re.IGNORECASE), "we're a family", "warn"),
    (re.compile(r"\bwork hard,?\s+play hard\b", re.IGNORECASE), "work hard, play hard", "warn"),
    (re.compile(r"\bwear (?:many|multiple) hats\b", re.IGNORECASE), "wear many hats", "info"),
    (re.compile(r"\b(?:must be |should be )?passionate about\b", re.IGNORECASE), "passionate about", "info"),
    (re.compile(r"\b(?:no )?work[- ]life balance\b", re.IGNORECASE), "work-life balance (mention)", "info"),
    (re.compile(r"\bfast[- ]paced environment\b", re.IGNORECASE), "fast-paced environment", "info"),
    (re.compile(r"\b(?:flexible|unlimited) (?:hours|pto|vacation)\b", re.IGNORECASE), "unlimited PTO/hours", "info"),
)

# Urgency: ASAP-style pressure correlates with poor planning, not legality
# issue, so info-level. Useful flag for candidate to negotiate timeline.
_URGENCY: Final[tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]] = (
    (re.compile(r"\basap\b", re.IGNORECASE), "ASAP", "info"),
    (re.compile(r"\bimmediate (?:start|joiner|joining)\b", re.IGNORECASE), "immediate start", "info"),
    (re.compile(r"\bstart yesterday\b", re.IGNORECASE), "start yesterday", "info"),
    (re.compile(r"\burgent(?:ly)? (?:hire|hiring|need)\b", re.IGNORECASE), "urgent hire", "info"),
)

_TABLES: Final[dict[AntiPatternCategory, tuple[tuple[re.Pattern[str], str, AntiPatternSeverity], ...]]] = {
    "ageist": _AGEIST,
    "gendered": _GENDERED,
    "vague_compensation": _VAGUE_COMP,
    "unrealistic_experience": _UNREALISTIC_EXP,
    "culture_red_flag": _CULTURE,
    "urgency": _URGENCY,
}


# ── Helpers ──────────────────────────────────────────────────────────


def _snippet_for(text: str, start: int, end: int) -> str:
    """±SNIPPET_RADIUS window with whitespace collapsed and ellipses on truncation.

    Char offsets are over ``text`` as-is (not lowercased) so the snippet
    preserves the user's casing and punctuation for the UI to render.
    """
    lo = max(0, start - SNIPPET_RADIUS)
    hi = min(len(text), end + SNIPPET_RADIUS)
    chunk = text[lo:hi]
    chunk = re.sub(r"\s+", " ", chunk).strip()
    if len(chunk) > MAX_SNIPPET_LEN:
        chunk = chunk[: MAX_SNIPPET_LEN - 1] + "…"
    prefix = "…" if lo > 0 else ""
    suffix = "…" if hi < len(text) else ""
    return f"{prefix}{chunk}{suffix}"


def _passes_unrealistic_threshold(match: re.Match[str]) -> bool:
    """For the unrealistic-experience table, gate on captured digits >= threshold.

    Matches like "5 years experience" don't qualify; "20+ years Python" does.
    Returns True for non-digit-capturing matches so other categories aren't
    affected by this helper if it ever gets reused.
    """
    try:
        digits = match.group(1)
    except IndexError:
        return True
    if digits is None or not digits.isdigit():
        return True
    return int(digits) >= UNREALISTIC_YEARS_THRESHOLD


# ── Public API ───────────────────────────────────────────────────────


def detect_anti_patterns(jd_text: str) -> AntiPatternReport:
    """Scan ``jd_text`` for recruiter anti-patterns; return a sorted report.

    Findings are sorted by (severity_rank, char_start) so the UI shows
    critical issues first while preserving source order within a bucket.
    Empty / whitespace input → empty report (no findings, all-zero counts).

    The function is total: any string in, an ``AntiPatternReport`` out.
    Non-string input raises TypeError at the boundary (cheap defence;
    the route layer already pydantic-validates).
    """
    if not isinstance(jd_text, str):
        raise TypeError("jd_text must be str")

    findings: list[Finding] = []
    by_category: dict[AntiPatternCategory, int] = {cat: 0 for cat in _TABLES}
    severity_counts: dict[AntiPatternSeverity, int] = {"critical": 0, "warn": 0, "info": 0}

    if not jd_text.strip():
        return AntiPatternReport(
            findings=tuple(),
            by_category=by_category,
            total_count=0,
            severity_counts=severity_counts,
        )

    for category, table in _TABLES.items():
        for pattern, term_label, severity in table:
            for match in pattern.finditer(jd_text):
                if category == "unrealistic_experience" and not _passes_unrealistic_threshold(match):
                    continue
                start, end = match.span()
                findings.append(
                    Finding(
                        category=category,
                        severity=severity,
                        snippet=_snippet_for(jd_text, start, end),
                        term=term_label,
                        char_start=start,
                        char_end=end,
                    )
                )
                by_category[category] += 1
                severity_counts[severity] += 1

    findings.sort(key=lambda f: (_SEVERITY_RANK[f.severity], f.char_start))

    return AntiPatternReport(
        findings=tuple(findings),
        by_category=by_category,
        total_count=len(findings),
        severity_counts=severity_counts,
    )


__all__ = [
    "AntiPatternCategory",
    "AntiPatternSeverity",
    "Finding",
    "AntiPatternReport",
    "detect_anti_patterns",
    "SNIPPET_RADIUS",
    "UNREALISTIC_YEARS_THRESHOLD",
]
